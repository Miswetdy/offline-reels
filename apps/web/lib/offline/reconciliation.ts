import { deleteCachedVideo, listCachedVideoIds, validateCachedVideo } from "./media-cache";
import { listOfflineVideos, updateOfflineVideo } from "./repository";
import type { OfflineErrorCode, OfflineVideoRecord } from "./types";

export type ReconciliationError = {
  scope: "record" | "cache";
  videoId?: string;
  code: OfflineErrorCode;
};

export type ReconciliationSummary = {
  interruptedMarkedFailed: number;
  missingCacheMarkedFailed: number;
  invalidCacheMarkedFailed: number;
  orphanCacheEntriesDeleted: number;
  validCompletedCount: number;
  storageUnavailable: boolean;
  errors: ReconciliationError[];
};

function emptySummary(): ReconciliationSummary {
  return {
    interruptedMarkedFailed: 0,
    missingCacheMarkedFailed: 0,
    invalidCacheMarkedFailed: 0,
    orphanCacheEntriesDeleted: 0,
    validCompletedCount: 0,
    storageUnavailable: false,
    errors: [],
  };
}

function errorCode(error: unknown): OfflineErrorCode {
  return typeof error === "object" && error !== null && "code" in error && typeof error.code === "string"
    ? (error.code as OfflineErrorCode)
    : "unknown_error";
}

async function markFailed(
  record: OfflineVideoRecord,
  code: OfflineErrorCode,
): Promise<OfflineVideoRecord | undefined> {
  return updateOfflineVideo(record.id, {
    status: "failed",
    downloadedBytes: 0,
    downloadedAt: null,
    cacheKey: null,
    lastErrorCode: code,
    lastErrorMessage:
      code === "download_interrupted"
        ? "The video download was interrupted before it finished."
        : "The local video file could not be validated.",
    failedAt: new Date().toISOString(),
  });
}

export async function reconcileOfflineLibrary(): Promise<ReconciliationSummary> {
  const summary = emptySummary();
  const records = await listOfflineVideos();
  // A cache entry belongs to the library only after its completed metadata and
  // its cached bytes both validate. Failed and interrupted records must not
  // retain media merely because their metadata still exists.
  const validCompletedIds = new Set<string>();

  for (const record of records) {
    try {
      if (record.status === "downloading") {
        try {
          await deleteCachedVideo(record.id);
        } catch (error) {
          summary.errors.push({ scope: "cache", videoId: record.id, code: errorCode(error) });
        }
        await markFailed(record, "download_interrupted");
        summary.interruptedMarkedFailed += 1;
        continue;
      }

      if (record.status !== "completed") continue;

      const validation = await validateCachedVideo(record.id, record);
      if (validation.valid) {
        validCompletedIds.add(record.id);
        summary.validCompletedCount += 1;
        continue;
      }

      if (validation.reason !== "missing") {
        try {
          await deleteCachedVideo(record.id);
        } catch (error) {
          summary.errors.push({ scope: "cache", videoId: record.id, code: errorCode(error) });
        }
      }
      await markFailed(record, validation.reason === "missing" ? "cache_entry_missing" : "cache_validation_failed");
      if (validation.reason === "missing") {
        summary.missingCacheMarkedFailed += 1;
      } else {
        summary.invalidCacheMarkedFailed += 1;
      }
    } catch (error) {
      const code = errorCode(error);
      if (code === "browser_storage_unavailable") summary.storageUnavailable = true;
      summary.errors.push({ scope: "record", videoId: record.id, code });
    }
  }

  try {
    for (const videoId of await listCachedVideoIds()) {
      if (validCompletedIds.has(videoId)) continue;
      try {
        const deleted = await deleteCachedVideo(videoId);
        if (deleted) summary.orphanCacheEntriesDeleted += 1;
      } catch (error) {
        summary.errors.push({ scope: "cache", videoId, code: errorCode(error) });
      }
    }
  } catch (error) {
    const code = errorCode(error);
    if (code === "browser_storage_unavailable") summary.storageUnavailable = true;
    summary.errors.push({ scope: "cache", code });
  }

  return summary;
}

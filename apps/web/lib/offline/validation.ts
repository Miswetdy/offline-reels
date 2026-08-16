import { OfflineStorageError } from "./errors";
import { getOfflineMediaPath, normalizeVideoId } from "./media-key";
import { OFFLINE_ERROR_CODES, OFFLINE_VIDEO_STATUSES, type OfflineVideoRecord } from "./types";

export function isAllowedVideoContentType(contentType: string): boolean {
  return contentType.split(";", 1)[0]?.trim().toLowerCase() === "video/mp4";
}

function isIsoDate(value: string | null): value is string {
  return value !== null && Number.isFinite(Date.parse(value));
}

function assertNullableIsoDate(value: string | null, field: string): void {
  if (value !== null && !isIsoDate(value)) {
    throw new OfflineStorageError("unknown_error", new Error(`${field} must be an ISO date.`));
  }
}

export function assertOfflineVideoRecord(record: OfflineVideoRecord): void {
  normalizeVideoId(record.id);

  if (record.title.trim().length === 0 || record.title.length > 255) {
    throw new OfflineStorageError("unknown_error", new Error("title is invalid."));
  }

  if (!isAllowedVideoContentType(record.contentType)) {
    throw new OfflineStorageError("unsupported_content_type");
  }

  if (!Number.isSafeInteger(record.byteSize) || record.byteSize <= 0) {
    throw new OfflineStorageError("byte_size_mismatch");
  }

  if (!OFFLINE_VIDEO_STATUSES.includes(record.status)) {
    throw new OfflineStorageError("unknown_error", new Error("status is invalid."));
  }

  if (!Number.isSafeInteger(record.downloadedBytes) || record.downloadedBytes < 0) {
    throw new OfflineStorageError("byte_size_mismatch");
  }

  if (!isIsoDate(record.createdAt) || !isIsoDate(record.updatedAt)) {
    throw new OfflineStorageError("unknown_error", new Error("record dates are invalid."));
  }

  assertNullableIsoDate(record.downloadedAt, "downloadedAt");
  assertNullableIsoDate(record.failedAt, "failedAt");
  assertNullableIsoDate(record.lastWatchedAt, "lastWatchedAt");
  assertNullableIsoDate(record.viewedAt ?? null, "viewedAt");
  assertNullableIsoDate(record.deleteAfter ?? null, "deleteAfter");

  if (record.viewedAt && (!record.deleteAfter || Date.parse(record.deleteAfter) < Date.parse(record.viewedAt))) {
    throw new OfflineStorageError("unknown_error", new Error("Viewed video must have an ordered delete deadline."));
  }
  if (record.deletionState && !["none", "pending", "deleting", "deleted", "failed"].includes(record.deletionState)) {
    throw new OfflineStorageError("unknown_error", new Error("deletionState is invalid."));
  }
  if (record.viewSyncState && !["none", "pending", "synced"].includes(record.viewSyncState)) {
    throw new OfflineStorageError("unknown_error", new Error("viewSyncState is invalid."));
  }
  if (record.viewSyncAttempts !== undefined && (!Number.isInteger(record.viewSyncAttempts) || record.viewSyncAttempts < 0 || record.viewSyncAttempts > 8)) {
    throw new OfflineStorageError("unknown_error", new Error("viewSyncAttempts is invalid."));
  }

  if (record.cacheKey !== null && record.cacheKey !== getOfflineMediaPath(record.id)) {
    throw new OfflineStorageError("invalid_video_id");
  }

  if (record.lastErrorCode !== null && !OFFLINE_ERROR_CODES.includes(record.lastErrorCode)) {
    throw new OfflineStorageError("unknown_error", new Error("lastErrorCode is invalid."));
  }

  if (record.lastErrorMessage !== null && record.lastErrorMessage.length > 500) {
    throw new OfflineStorageError("unknown_error", new Error("lastErrorMessage is too long."));
  }

  if (record.status === "completed") {
    if (record.cacheKey === null || record.downloadedAt === null || record.downloadedBytes !== record.byteSize) {
      throw new OfflineStorageError("cache_validation_failed");
    }
  }
}

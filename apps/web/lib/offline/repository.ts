import { OfflineStorageError, toOfflineStorageError } from "./errors";
import { normalizeVideoId } from "./media-key";
import { OFFLINE_VIDEO_STORE, withOfflineDatabase } from "./db";
import { assertOfflineVideoRecord } from "./validation";
import type { OfflineVideoPatch, OfflineVideoRecord, OfflineVideoStatus } from "./types";

type OfflineVideoUpdater = OfflineVideoPatch | ((record: OfflineVideoRecord) => OfflineVideoPatch);

function nowIso(): string {
  return new Date().toISOString();
}

function sortByUpdatedAt(left: OfflineVideoRecord, right: OfflineVideoRecord): number {
  return right.updatedAt.localeCompare(left.updatedAt) || right.id.localeCompare(left.id);
}

function sortCompleted(left: OfflineVideoRecord, right: OfflineVideoRecord): number {
  return (right.downloadedAt ?? "").localeCompare(left.downloadedAt ?? "") || right.id.localeCompare(left.id);
}

export async function getOfflineVideo(videoId: string): Promise<OfflineVideoRecord | undefined> {
  const id = normalizeVideoId(videoId);
  return withOfflineDatabase((database) => database.get(OFFLINE_VIDEO_STORE, id));
}

export async function listOfflineVideos(): Promise<OfflineVideoRecord[]> {
  const records = await withOfflineDatabase((database) => database.getAll(OFFLINE_VIDEO_STORE));
  return records.sort(sortByUpdatedAt);
}

export async function listCompletedOfflineVideos(): Promise<OfflineVideoRecord[]> {
  const records = await listOfflineVideos();
  return records.filter((record) => record.status === "completed").sort(sortCompleted);
}

export async function listOfflineVideosByStatus(status: OfflineVideoStatus): Promise<OfflineVideoRecord[]> {
  const records = await withOfflineDatabase((database) =>
    database.getAllFromIndex(OFFLINE_VIDEO_STORE, "statusUpdatedAt", IDBKeyRange.bound([status, ""], [status, "\uffff"])),
  );
  return records.sort(sortByUpdatedAt);
}

export async function putOfflineVideo(record: OfflineVideoRecord): Promise<void> {
  const normalized = { ...record, id: normalizeVideoId(record.id) };
  assertOfflineVideoRecord(normalized);
  await withOfflineDatabase(async (database) => {
    await database.put(OFFLINE_VIDEO_STORE, normalized);
  });
}

export async function updateOfflineVideo(
  videoId: string,
  updater: OfflineVideoUpdater,
): Promise<OfflineVideoRecord | undefined> {
  const id = normalizeVideoId(videoId);

  return withOfflineDatabase(async (database) => {
    const existing = await database.get(OFFLINE_VIDEO_STORE, id);
    if (!existing) return undefined;

    const patch = typeof updater === "function" ? updater(existing) : updater;
    const updated: OfflineVideoRecord = { ...existing, ...patch, id, updatedAt: nowIso() };
    assertOfflineVideoRecord(updated);
    await database.put(OFFLINE_VIDEO_STORE, updated);
    return updated;
  });
}

export async function deleteOfflineVideo(videoId: string): Promise<void> {
  const id = normalizeVideoId(videoId);
  await withOfflineDatabase(async (database) => {
    await database.delete(OFFLINE_VIDEO_STORE, id);
  });
}

export async function clearOfflineVideos(): Promise<void> {
  await withOfflineDatabase(async (database) => {
    await database.clear(OFFLINE_VIDEO_STORE);
  });
}

export async function markInterruptedDownloadsFailed(): Promise<OfflineVideoRecord[]> {
  const downloading = await listOfflineVideosByStatus("downloading");
  const timestamp = nowIso();
  const updatedRecords: OfflineVideoRecord[] = [];

  for (const record of downloading) {
    const updated = await updateOfflineVideo(record.id, {
      status: "failed",
      downloadedBytes: 0,
      downloadedAt: null,
      cacheKey: null,
      lastErrorCode: "download_interrupted",
      lastErrorMessage: "The video download was interrupted before it finished.",
      failedAt: timestamp,
    });

    if (!updated) {
      throw new OfflineStorageError("unknown_error");
    }
    updatedRecords.push(updated);
  }

  return updatedRecords;
}

export async function calculateCompletedLibrarySize(): Promise<number> {
  const completed = await listCompletedOfflineVideos();
  return completed.reduce((total, record) => total + record.byteSize, 0);
}

export function normalizeRepositoryError(error: unknown): OfflineStorageError {
  return toOfflineStorageError(error);
}

import "fake-indexeddb/auto";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OFFLINE_DATABASE_NAME, OFFLINE_VIDEO_STORE, openOfflineDatabase } from "../../lib/offline/db";
import { OfflineStorageError } from "../../lib/offline/errors";
import { getOfflineMediaPath } from "../../lib/offline/media-key";
import {
  calculateCompletedLibrarySize,
  clearOfflineVideos,
  deleteOfflineVideo,
  getOfflineVideo,
  listCompletedOfflineVideos,
  listOfflineVideos,
  listOfflineVideosByStatus,
  markInterruptedDownloadsFailed,
  putOfflineVideo,
  updateOfflineVideo,
} from "../../lib/offline/repository";
import type { OfflineVideoRecord } from "../../lib/offline/types";
import { resetOfflineDatabase, VIDEO_ID_ONE, VIDEO_ID_TWO } from "./test-helpers";

function record(id = VIDEO_ID_ONE, overrides: Partial<OfflineVideoRecord> = {}): OfflineVideoRecord {
  const timestamp = "2026-07-22T12:00:00.000Z";
  return {
    id,
    title: "Offline video",
    contentType: "video/mp4",
    byteSize: 100,
    createdAt: timestamp,
    status: "queued",
    downloadedBytes: 0,
    downloadedAt: null,
    cacheKey: null,
    lastErrorCode: null,
    lastErrorMessage: null,
    failedAt: null,
    lastWatchedAt: null,
    updatedAt: timestamp,
    ...overrides,
  };
}

beforeEach(async () => {
  await resetOfflineDatabase();
});

afterEach(async () => {
  vi.unstubAllGlobals();
  await resetOfflineDatabase();
});

describe("offline IndexedDB repository", () => {
  it("creates schema v1 with the required store and indexes", async () => {
    const database = await openOfflineDatabase();
    expect(database.name).toBe(OFFLINE_DATABASE_NAME);
    expect(database.version).toBe(2);
    expect([...database.objectStoreNames]).toContain(OFFLINE_VIDEO_STORE);
    const transaction = database.transaction(OFFLINE_VIDEO_STORE);
    expect([...transaction.store.indexNames].sort()).toEqual(
      ["completedDownloadedAt", "lastWatchedAt", "statusUpdatedAt"].sort(),
    );
    database.close();
  });

  it("puts, gets, upserts, lists, updates and deletes records", async () => {
    await putOfflineVideo(record());
    expect((await getOfflineVideo(VIDEO_ID_ONE))?.title).toBe("Offline video");

    await putOfflineVideo(record(VIDEO_ID_ONE, { title: "Updated title" }));
    expect((await listOfflineVideos()).map((item) => item.title)).toEqual(["Updated title"]);

    const updated = await updateOfflineVideo(VIDEO_ID_ONE, { status: "failed", lastErrorCode: "network_error" });
    expect(updated?.status).toBe("failed");
    expect(updated?.updatedAt).not.toBe("2026-07-22T12:00:00.000Z");
    expect(await updateOfflineVideo(VIDEO_ID_TWO, { title: "missing" })).toBeUndefined();

    await deleteOfflineVideo(VIDEO_ID_ONE);
    expect(await getOfflineVideo(VIDEO_ID_ONE)).toBeUndefined();
  });

  it("lists by status, marks interrupted downloads failed, and clears records", async () => {
    await putOfflineVideo(record(VIDEO_ID_ONE, { status: "downloading", downloadedBytes: 25 }));
    await putOfflineVideo(record(VIDEO_ID_TWO, { status: "failed", lastErrorCode: "network_error" }));

    expect(await listOfflineVideosByStatus("downloading")).toHaveLength(1);
    const interrupted = await markInterruptedDownloadsFailed();
    expect(interrupted).toHaveLength(1);
    expect(interrupted[0]).toMatchObject({
      status: "failed",
      downloadedBytes: 0,
      cacheKey: null,
      lastErrorCode: "download_interrupted",
    });

    await clearOfflineVideos();
    expect(await listOfflineVideos()).toEqual([]);
  });

  it("calculates exact completed-library size and persists across database openings", async () => {
    await putOfflineVideo(
      record(VIDEO_ID_ONE, {
        status: "completed",
        byteSize: 100,
        downloadedBytes: 100,
        downloadedAt: "2026-07-22T13:00:00.000Z",
        cacheKey: getOfflineMediaPath(VIDEO_ID_ONE),
      }),
    );
    await putOfflineVideo(
      record(VIDEO_ID_TWO, {
        status: "completed",
        byteSize: 200,
        downloadedBytes: 200,
        downloadedAt: "2026-07-22T14:00:00.000Z",
        cacheKey: getOfflineMediaPath(VIDEO_ID_TWO),
      }),
    );

    expect(await calculateCompletedLibrarySize()).toBe(300);
    expect((await listCompletedOfflineVideos()).map((item) => item.id)).toEqual([VIDEO_ID_TWO, VIDEO_ID_ONE]);
    expect(await getOfflineVideo(VIDEO_ID_ONE)).toBeDefined();
  });

  it("does not invoke browser APIs at import time and reports unavailable IndexedDB at call time", async () => {
    vi.stubGlobal("indexedDB", undefined);
    await expect(getOfflineVideo(VIDEO_ID_ONE)).rejects.toMatchObject({
      code: "browser_storage_unavailable",
    });
  });
});

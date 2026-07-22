import "fake-indexeddb/auto";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getOfflineMediaPath } from "../../lib/offline/media-key";
import {
  OFFLINE_MEDIA_CACHE_NAME,
  getCachedVideo,
  getMediaCacheKey,
  hasCachedVideo,
  putCachedVideo,
} from "../../lib/offline/media-cache";
import { reconcileOfflineLibrary } from "../../lib/offline/reconciliation";
import { getOfflineVideo, putOfflineVideo } from "../../lib/offline/repository";
import type { OfflineVideoRecord } from "../../lib/offline/types";
import { VIDEO_ID_ONE, VIDEO_ID_THREE, VIDEO_ID_TWO, installFakeCacheStorage, resetOfflineDatabase, videoResponse } from "./test-helpers";

function record(id: string, overrides: Partial<OfflineVideoRecord> = {}): OfflineVideoRecord {
  const timestamp = "2026-07-22T12:00:00.000Z";
  return {
    id,
    title: "Offline video",
    contentType: "video/mp4",
    byteSize: 4,
    createdAt: timestamp,
    status: "completed",
    downloadedBytes: 4,
    downloadedAt: timestamp,
    cacheKey: getOfflineMediaPath(id),
    lastErrorCode: null,
    lastErrorMessage: null,
    failedAt: null,
    lastWatchedAt: null,
    updatedAt: timestamp,
    ...overrides,
  };
}

beforeEach(async () => {
  installFakeCacheStorage();
  await resetOfflineDatabase();
});

afterEach(async () => {
  await resetOfflineDatabase();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(globalThis, "caches");
});

describe("offline-library reconciliation", () => {
  it("marks stale downloads failed and removes their possible cache entry", async () => {
    await putOfflineVideo(record(VIDEO_ID_ONE, { status: "downloading", downloadedBytes: 2, downloadedAt: null, cacheKey: null }));
    await putCachedVideo(VIDEO_ID_ONE, videoResponse(4));

    const summary = await reconcileOfflineLibrary();
    expect(summary.interruptedMarkedFailed).toBe(1);
    expect(await getOfflineVideo(VIDEO_ID_ONE)).toMatchObject({ status: "failed", lastErrorCode: "download_interrupted" });
    expect(await hasCachedVideo(VIDEO_ID_ONE)).toBe(false);
  });

  it("marks missing and invalid completed cache entries failed without affecting valid records", async () => {
    await putOfflineVideo(record(VIDEO_ID_ONE));
    await putOfflineVideo(record(VIDEO_ID_TWO));
    await putOfflineVideo(record(VIDEO_ID_THREE));
    await putCachedVideo(VIDEO_ID_TWO, videoResponse(3));
    await putCachedVideo(VIDEO_ID_THREE, videoResponse(4));

    const summary = await reconcileOfflineLibrary();
    expect(summary).toMatchObject({ missingCacheMarkedFailed: 1, invalidCacheMarkedFailed: 1, validCompletedCount: 1 });
    expect(await getOfflineVideo(VIDEO_ID_ONE)).toMatchObject({ status: "failed", lastErrorCode: "cache_entry_missing" });
    expect(await getOfflineVideo(VIDEO_ID_TWO)).toMatchObject({ status: "failed", lastErrorCode: "cache_validation_failed" });
    expect(await getOfflineVideo(VIDEO_ID_THREE)).toMatchObject({ status: "completed" });
    expect(await hasCachedVideo(VIDEO_ID_TWO)).toBe(false);
  });

  it("deletes orphan cache entries and is idempotent", async () => {
    await putCachedVideo(VIDEO_ID_ONE, videoResponse(4));
    const first = await reconcileOfflineLibrary();
    const second = await reconcileOfflineLibrary();

    expect(first.orphanCacheEntriesDeleted).toBe(1);
    expect(await getCachedVideo(VIDEO_ID_ONE)).toBeUndefined();
    expect(second).toMatchObject({ orphanCacheEntriesDeleted: 0, validCompletedCount: 0, errors: [] });
  });

  it("removes completed entries with an invalid cached content type", async () => {
    await putOfflineVideo(record(VIDEO_ID_ONE));
    const cache = await caches.open(OFFLINE_MEDIA_CACHE_NAME);
    await cache.put(getMediaCacheKey(VIDEO_ID_ONE), videoResponse(4, "text/plain"));

    const summary = await reconcileOfflineLibrary();
    expect(summary.invalidCacheMarkedFailed).toBe(1);
    expect(await getOfflineVideo(VIDEO_ID_ONE)).toMatchObject({ status: "failed", lastErrorCode: "cache_validation_failed" });
    expect(await hasCachedVideo(VIDEO_ID_ONE)).toBe(false);
  });
});

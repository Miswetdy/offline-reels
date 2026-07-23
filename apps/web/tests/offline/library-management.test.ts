import "fake-indexeddb/auto";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OFFLINE_MEDIA_CACHE_NAME, getCachedVideo, putCachedVideo } from "../../lib/offline/media-cache";
import { clearOfflineLibrary, deleteOfflineLibraryVideo } from "../../lib/offline/library-management";
import { getOfflineVideo, putOfflineVideo } from "../../lib/offline/repository";
import type { OfflineVideoRecord } from "../../lib/offline/types";
import { VIDEO_ID_ONE, VIDEO_ID_TWO, installFakeCacheStorage, resetOfflineDatabase, videoResponse } from "./test-helpers";

function record(id: string): OfflineVideoRecord {
  const timestamp = "2026-07-23T12:00:00.000Z";
  return {
    id, title: "Offline video", contentType: "video/mp4", byteSize: 4, createdAt: timestamp,
    status: "completed", downloadedBytes: 4, downloadedAt: timestamp, cacheKey: `/offline-media/${id}`,
    lastErrorCode: null, lastErrorMessage: null, failedAt: null, lastWatchedAt: null, updatedAt: timestamp,
  };
}

beforeEach(async () => { installFakeCacheStorage(); await resetOfflineDatabase(); });
afterEach(async () => { await resetOfflineDatabase(); vi.unstubAllGlobals(); Reflect.deleteProperty(globalThis, "caches"); });

describe("offline library management", () => {
  it("deletes cache metadata idempotently without any backend request", async () => {
    await putOfflineVideo(record(VIDEO_ID_ONE));
    await putCachedVideo(VIDEO_ID_ONE, videoResponse(4));
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    await deleteOfflineLibraryVideo(VIDEO_ID_ONE);
    await deleteOfflineLibraryVideo(VIDEO_ID_ONE);
    expect(await getCachedVideo(VIDEO_ID_ONE)).toBeUndefined();
    expect(await getOfflineVideo(VIDEO_ID_ONE)).toBeUndefined();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("clears only the media cache and offline records", async () => {
    const storage = installFakeCacheStorage();
    const other = await storage.open("application-shell");
    await other.put("/shell", new Response("shell"));
    await putOfflineVideo(record(VIDEO_ID_ONE));
    await putOfflineVideo(record(VIDEO_ID_TWO));
    await putCachedVideo(VIDEO_ID_ONE, videoResponse(4));
    await putCachedVideo(VIDEO_ID_TWO, videoResponse(4));
    await clearOfflineLibrary();
    expect(await getOfflineVideo(VIDEO_ID_ONE)).toBeUndefined();
    expect(await getOfflineVideo(VIDEO_ID_TWO)).toBeUndefined();
    expect(await storage.has(OFFLINE_MEDIA_CACHE_NAME)).toBe(false);
    expect(await storage.has("application-shell")).toBe(true);
  });
});

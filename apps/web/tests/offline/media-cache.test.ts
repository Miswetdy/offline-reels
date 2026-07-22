import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OfflineStorageError } from "../../lib/offline/errors";
import {
  OFFLINE_MEDIA_CACHE_NAME,
  clearMediaCache,
  deleteCachedVideo,
  getCachedVideo,
  getMediaCacheKey,
  hasCachedVideo,
  listCachedVideoIds,
  putCachedVideo,
  validateCachedVideo,
} from "../../lib/offline/media-cache";
import { VIDEO_ID_ONE, VIDEO_ID_TWO, installFakeCacheStorage, videoResponse } from "./test-helpers";

beforeEach(() => {
  installFakeCacheStorage();
});

afterEach(() => {
  vi.unstubAllGlobals();
  Reflect.deleteProperty(globalThis, "caches");
});

describe("offline media cache", () => {
  it("stores, reads, lists and deletes media by its synthetic key", async () => {
    const source = videoResponse(4);
    await putCachedVideo(VIDEO_ID_ONE, source);
    expect((await source.blob()).size).toBe(4);
    expect(getMediaCacheKey(VIDEO_ID_ONE)).toBe(`/offline-media/${VIDEO_ID_ONE}`);
    expect(await hasCachedVideo(VIDEO_ID_ONE)).toBe(true);
    expect((await getCachedVideo(VIDEO_ID_ONE))?.headers.get("content-type")).toBe("video/mp4");
    expect(await listCachedVideoIds()).toEqual([VIDEO_ID_ONE]);
    expect(await deleteCachedVideo(VIDEO_ID_ONE)).toBe(true);
    expect(await getCachedVideo(VIDEO_ID_ONE)).toBeUndefined();
  });

  it("clears only the TASK-005 media cache", async () => {
    const storage = installFakeCacheStorage();
    const shell = await storage.open("application-shell");
    await shell.put("/shell", new Response("shell"));
    await putCachedVideo(VIDEO_ID_ONE, videoResponse(4));

    expect(await clearMediaCache()).toBe(true);
    expect(await storage.has(OFFLINE_MEDIA_CACHE_NAME)).toBe(false);
    expect(await storage.has("application-shell")).toBe(true);
  });

  it("rejects unexpected media types and invalid identifiers", async () => {
    await expect(putCachedVideo(VIDEO_ID_ONE, videoResponse(4, "text/plain"))).rejects.toMatchObject({
      code: "unsupported_content_type",
    });
    await expect(putCachedVideo("../../unsafe", videoResponse(4))).rejects.toMatchObject({ code: "invalid_video_id" });
  });

  it("validates cache key, content type, cache hit and exact byte size", async () => {
    await putCachedVideo(VIDEO_ID_ONE, videoResponse(4));
    await expect(
      validateCachedVideo(VIDEO_ID_ONE, { cacheKey: getMediaCacheKey(VIDEO_ID_ONE), contentType: "video/mp4", byteSize: 4 }),
    ).resolves.toEqual({ valid: true, byteSize: 4 });
    await expect(
      validateCachedVideo(VIDEO_ID_ONE, { cacheKey: getMediaCacheKey(VIDEO_ID_ONE), contentType: "video/mp4", byteSize: 5 }),
    ).resolves.toEqual({ valid: false, reason: "size_mismatch" });
    await expect(
      validateCachedVideo(VIDEO_ID_TWO, { cacheKey: getMediaCacheKey(VIDEO_ID_TWO), contentType: "video/mp4", byteSize: 4 }),
    ).resolves.toEqual({ valid: false, reason: "missing" });
    await expect(
      validateCachedVideo(VIDEO_ID_ONE, { cacheKey: getMediaCacheKey(VIDEO_ID_TWO), contentType: "video/mp4", byteSize: 4 }),
    ).resolves.toEqual({ valid: false, reason: "cache_key_mismatch" });
  });

  it("reports unavailable Cache Storage as a typed error", async () => {
    vi.stubGlobal("caches", undefined);
    await expect(hasCachedVideo(VIDEO_ID_ONE)).rejects.toMatchObject({
      code: "browser_storage_unavailable",
    });
  });
});

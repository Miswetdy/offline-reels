import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OfflineStorageError } from "../../lib/offline/errors";
import { putCachedVideo } from "../../lib/offline/media-cache";
import { createOfflinePlaybackSource } from "../../lib/offline/playback-source";
import { VIDEO_ID_ONE, installFakeCacheStorage, videoResponse } from "./test-helpers";

beforeEach(() => {
  installFakeCacheStorage();
  Object.defineProperties(URL, {
    createObjectURL: { configurable: true, value: vi.fn(() => "blob:offline-one") },
    revokeObjectURL: { configurable: true, value: vi.fn() },
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  Reflect.deleteProperty(URL, "createObjectURL");
  Reflect.deleteProperty(URL, "revokeObjectURL");
  Reflect.deleteProperty(globalThis, "caches");
});

describe("offline playback source", () => {
  it("creates a temporary object URL from cached MP4 and revokes it once", async () => {
    await putCachedVideo(VIDEO_ID_ONE, videoResponse(4));

    const source = await createOfflinePlaybackSource(VIDEO_ID_ONE);
    expect(source.url).toBe("blob:offline-one");
    expect(URL.createObjectURL).toHaveBeenCalledOnce();
    source.revoke();
    source.revoke();
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(1);
  });

  it("does not fall back to backend when the cache entry is missing or invalid", async () => {
    await expect(createOfflinePlaybackSource(VIDEO_ID_ONE)).rejects.toMatchObject({ code: "cache_entry_missing" });
    await putCachedVideo(VIDEO_ID_ONE, videoResponse(4, "video/mp4"));
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: undefined });
    await expect(createOfflinePlaybackSource(VIDEO_ID_ONE)).rejects.toBeInstanceOf(OfflineStorageError);
  });
});

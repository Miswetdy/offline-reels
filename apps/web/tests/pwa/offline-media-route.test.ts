import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OFFLINE_MEDIA_CACHE_NAME, putCachedVideo } from "../../lib/offline/media-cache";
import {
  getOfflineMediaRouteVideoId,
  handleOfflineMediaRequest,
  parseSingleByteRange,
  shouldHandleOfflineMediaRequest,
} from "../../lib/pwa/offline-media-route";
import { VIDEO_ID_ONE, installFakeCacheStorage } from "../offline/test-helpers";

const applicationOrigin = "https://offline-reels.test";

function request(path: string, init?: RequestInit): Request {
  return new Request(new URL(path, applicationOrigin), init);
}

beforeEach(() => {
  installFakeCacheStorage();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(globalThis, "caches");
});

describe("offline media Service Worker route", () => {
  it("returns the full cached MP4 response without using fetch or shell caches", async () => {
    const storage = installFakeCacheStorage();
    const shellCache = await storage.open("serwist-precache-shell");
    await shellCache.put("/offline-media/shell", new Response("shell"));
    await putCachedVideo(
      VIDEO_ID_ONE,
      new Response(new Uint8Array([1, 2, 3, 4]), {
        headers: { "content-type": "video/mp4", "content-length": "4" },
      }),
    );
    const fetch = vi.spyOn(globalThis, "fetch");

    const response = await handleOfflineMediaRequest(request(`/offline-media/${VIDEO_ID_ONE}`));

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("video/mp4");
    expect(response.headers.get("content-length")).toBe("4");
    expect(response.headers.get("accept-ranges")).toBe("bytes");
    expect([...new Uint8Array(await response.arrayBuffer())]).toEqual([1, 2, 3, 4]);
    expect(await storage.has(OFFLINE_MEDIA_CACHE_NAME)).toBe(true);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("returns precise 206 slices for closed, open-ended, and suffix ranges without mutating cached media", async () => {
    await putCachedVideo(
      VIDEO_ID_ONE,
      new Response(new Uint8Array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]), {
        headers: { "content-type": "video/mp4", "content-length": "10", etag: "test-etag" },
      }),
    );

    const closed = await handleOfflineMediaRequest(request(`/offline-media/${VIDEO_ID_ONE}`, { headers: { range: "bytes=2-5" } }));
    expect(closed.status).toBe(206);
    expect(closed.headers.get("content-range")).toBe("bytes 2-5/10");
    expect(closed.headers.get("content-length")).toBe("4");
    expect(closed.headers.get("accept-ranges")).toBe("bytes");
    expect(closed.headers.get("etag")).toBe("test-etag");
    expect([...new Uint8Array(await closed.arrayBuffer())]).toEqual([2, 3, 4, 5]);

    const openEnded = await handleOfflineMediaRequest(request(`/offline-media/${VIDEO_ID_ONE}`, { headers: { range: "bytes=7-" } }));
    expect(openEnded.headers.get("content-range")).toBe("bytes 7-9/10");
    expect([...new Uint8Array(await openEnded.arrayBuffer())]).toEqual([7, 8, 9]);

    const suffix = await handleOfflineMediaRequest(request(`/offline-media/${VIDEO_ID_ONE}`, { headers: { range: "bytes=-3" } }));
    expect(suffix.headers.get("content-range")).toBe("bytes 7-9/10");
    expect([...new Uint8Array(await suffix.arrayBuffer())]).toEqual([7, 8, 9]);

    const fullAgain = await handleOfflineMediaRequest(request(`/offline-media/${VIDEO_ID_ONE}`));
    expect([...new Uint8Array(await fullAgain.arrayBuffer())]).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
  });

  it("reads a cached response body once per request and does not retain or rewrite the slice", async () => {
    const cached = new Response(new Uint8Array([0, 1, 2, 3]), { headers: { "content-type": "video/mp4" } });
    const arrayBuffer = vi.spyOn(cached, "arrayBuffer");
    const cache = { match: vi.fn().mockResolvedValue(cached) };
    const storage = { open: vi.fn().mockResolvedValue(cache) };

    const response = await handleOfflineMediaRequest(
      request(`/offline-media/${VIDEO_ID_ONE}`, { headers: { range: "bytes=1-2" } }),
      storage,
    );

    expect(response.status).toBe(206);
    expect([...new Uint8Array(await response.arrayBuffer())]).toEqual([1, 2]);
    expect(arrayBuffer).toHaveBeenCalledOnce();
    expect(cache.match).toHaveBeenCalledOnce();
    expect(storage.open).toHaveBeenCalledWith(OFFLINE_MEDIA_CACHE_NAME);
  });

  it("returns 416 with total size for cache hits with malformed, multipart, or unsatisfiable ranges", async () => {
    await putCachedVideo(VIDEO_ID_ONE, new Response(new Uint8Array([0, 1, 2, 3]), { headers: { "content-type": "video/mp4" } }));
    for (const range of ["bytes=4-", "bytes=99-100", "bytes=-0", "bytes=3-2", "bytes=0-1,2-3", "items=0-1", "bytes="]) {
      const response = await handleOfflineMediaRequest(request(`/offline-media/${VIDEO_ID_ONE}`, { headers: { range } }));
      expect(response.status).toBe(416);
      expect(response.headers.get("content-range")).toBe("bytes */4");
    }
  });

  it("returns controlled 404 for cache misses and supports metadata-only HEAD responses", async () => {
    await expect(handleOfflineMediaRequest(request(`/offline-media/${VIDEO_ID_ONE}`))).resolves.toMatchObject({ status: 404 });
    await putCachedVideo(VIDEO_ID_ONE, new Response(new Uint8Array([1, 2, 3, 4]), { headers: { "content-type": "video/mp4" } }));
    await expect(
      handleOfflineMediaRequest(request(`/offline-media/${VIDEO_ID_ONE}`, { method: "HEAD", headers: { range: "bytes=0-1" } })),
    ).resolves.toMatchObject({ status: 206 });
    const head = await handleOfflineMediaRequest(request(`/offline-media/${VIDEO_ID_ONE}`, { method: "HEAD" }));
    expect(head.headers.get("content-length")).toBe("4");
    expect(await head.text()).toBe("");
  });

  it("matches only same-origin GET requests with an exact valid synthetic path", () => {
    const validUrl = new URL(`/offline-media/${VIDEO_ID_ONE}`, applicationOrigin);
    expect(getOfflineMediaRouteVideoId(validUrl)).toBe(VIDEO_ID_ONE);
    expect(getOfflineMediaRouteVideoId(new URL("/offline-media/not-a-video", applicationOrigin))).toBeNull();
    expect(getOfflineMediaRouteVideoId(new URL(`/offline-media/${VIDEO_ID_ONE}?query=1`, applicationOrigin))).toBeNull();
    expect(shouldHandleOfflineMediaRequest({ request: request(`/offline-media/${VIDEO_ID_ONE}`), url: validUrl, sameOrigin: true })).toBe(true);
    expect(shouldHandleOfflineMediaRequest({ request: request(`/offline-media/${VIDEO_ID_ONE}`, { method: "HEAD" }), url: validUrl, sameOrigin: true })).toBe(true);
    expect(shouldHandleOfflineMediaRequest({ request: request(`/offline-media/${VIDEO_ID_ONE}`), url: validUrl, sameOrigin: false })).toBe(false);
  });

  it.each([
    ["bytes=0-", 10, { start: 0, end: 9 }],
    ["bytes=0-99", 10, { start: 0, end: 9 }],
    ["bytes=3-", 10, { start: 3, end: 9 }],
    ["bytes=-3", 10, { start: 7, end: 9 }],
    ["bytes=-99", 10, { start: 0, end: 9 }],
  ])("parses supported single range %s", (header, totalSize, expected) => {
    expect(parseSingleByteRange(header, totalSize)).toEqual(expected);
  });

  it.each([
    ["bytes=10-", 10],
    ["bytes=11-", 10],
    ["bytes=-0", 10],
    ["", 10],
    ["items=0-1", 10],
    ["bytes=not-a-number", 10],
    ["bytes=0-1,2-3", 10],
    ["bytes=9007199254740992-", 10],
    ["bytes=0-", 0],
  ])("rejects invalid or unsatisfiable single range %s", (header, totalSize) => {
    expect(parseSingleByteRange(header, totalSize)).toBeNull();
  });
});

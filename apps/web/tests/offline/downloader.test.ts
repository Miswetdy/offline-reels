import "fake-indexeddb/auto";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { downloadVideoForOffline, type DownloaderDependencies } from "../../lib/offline/downloader";
import { OfflineStorageError } from "../../lib/offline/errors";
import { getOfflineMediaPath } from "../../lib/offline/media-key";
import type { OfflineVideoRecord } from "../../lib/offline/types";
import { VIDEO_ID_ONE, videoResponse } from "./test-helpers";

const video = {
  id: VIDEO_ID_ONE,
  title: "Download target",
  content_type: "video/mp4",
  byte_size: 6,
  created_at: "2026-07-22T12:00:00.000Z",
};

function responseFromChunks(chunks: Uint8Array[], headers: HeadersInit = { "content-type": "video/mp4", "content-length": "6" }) {
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        chunks.forEach((chunk) => controller.enqueue(chunk));
        controller.close();
      },
    }),
    { status: 200, headers },
  );
}

function createHarness(overrides: Partial<DownloaderDependencies> = {}) {
  const records = new Map<string, OfflineVideoRecord>();
  const cache = new Map<string, Response>();
  const ownedResponses: Response[] = [];
  let timestamp = 0;
  const dependencies: Partial<DownloaderDependencies> = {
    fetchImplementation: vi.fn().mockResolvedValue(responseFromChunks([new Uint8Array([1, 2]), new Uint8Array([3, 4, 5, 6])])),
    getStorageEstimate: vi.fn().mockResolvedValue({ usage: 0, quota: 1_000_000_000, available: 1_000_000_000, isAvailable: true }),
    hasEstimatedSpaceForDownload: vi.fn().mockReturnValue(true),
    getOfflineVideo: vi.fn(async (id) => records.get(id)),
    putOfflineVideo: vi.fn(async (record) => void records.set(record.id, record)),
    updateOfflineVideo: vi.fn(async (id, patch) => {
      const previous = records.get(id);
      if (!previous) return undefined;
      const next = { ...previous, ...(typeof patch === "function" ? patch(previous) : patch), updatedAt: `2026-07-22T12:00:0${timestamp++}.000Z` };
      records.set(id, next);
      return next;
    }),
    deleteCachedVideo: vi.fn(async (id) => cache.delete(id)),
    putCachedVideoOwnedResponse: vi.fn(async (id, response) => {
      ownedResponses.push(response);
      const body = await response.arrayBuffer();
      cache.set(id, new Response(body, { headers: response.headers, status: response.status, statusText: response.statusText }));
    }),
    validateCachedVideo: vi.fn(async (id, expected) => {
      const response = cache.get(id);
      if (!response) return { valid: false as const, reason: "missing" as const };
      const size = (await response.clone().arrayBuffer()).byteLength;
      return size === expected.byteSize ? { valid: true as const, byteSize: size } : { valid: false as const, reason: "size_mismatch" as const };
    }),
    getStreamUrl: vi.fn((id) => `http://api.test/videos/${id}/stream`),
    now: () => "2026-07-22T12:00:00.000Z",
    progressIntervalMs: 100,
    ...overrides,
  };
  return { records, cache, ownedResponses, dependencies: dependencies as DownloaderDependencies };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("single-stream offline downloader", () => {
  it("passes chunks unchanged through one owned response, reports progress, validates cache, then completes metadata", async () => {
    const harness = createHarness();
    const progress: number[] = [];
    const result = await downloadVideoForOffline(
      { video, signal: new AbortController().signal, onProgress: (event) => progress.push(event.downloadedBytes) },
      harness.dependencies,
    );

    expect(result).toMatchObject({ status: "completed", downloadedBytes: 6, cacheKey: getOfflineMediaPath(VIDEO_ID_ONE) });
    expect(progress.at(-1)).toBe(6);
    expect(harness.ownedResponses).toHaveLength(1);
    expect(harness.ownedResponses[0].bodyUsed).toBe(true);
    expect(new Uint8Array(await harness.cache.get(VIDEO_ID_ONE)!.arrayBuffer())).toEqual(new Uint8Array([1, 2, 3, 4, 5, 6]));
    const validationOrder = (harness.dependencies.validateCachedVideo as ReturnType<typeof vi.fn>).mock.invocationCallOrder.at(-1)!;
    const completedCallIndex = (harness.dependencies.updateOfflineVideo as ReturnType<typeof vi.fn>).mock.calls.findIndex(
      ([, patch]) => patch.status === "completed",
    );
    const completedOrder = (harness.dependencies.updateOfflineVideo as ReturnType<typeof vi.fn>).mock.invocationCallOrder[completedCallIndex];
    expect(validationOrder).toBeLessThan(completedOrder);
  });

  it("throttles intermediate progress but never drops the exact final progress", async () => {
    const chunks = Array.from({ length: 6 }, () => new Uint8Array([1]));
    const harness = createHarness({ fetchImplementation: vi.fn().mockResolvedValue(responseFromChunks(chunks, { "content-type": "video/mp4", "content-length": "6" })) });
    const events: number[] = [];
    await downloadVideoForOffline({ video, signal: new AbortController().signal, onProgress: (event) => events.push(event.downloadedBytes) }, harness.dependencies);
    expect(events).toEqual([1, 6]);
  });

  it("uses indeterminate progress when Content-Length is absent", async () => {
    const harness = createHarness({ fetchImplementation: vi.fn().mockResolvedValue(responseFromChunks([new Uint8Array(6)], { "content-type": "video/mp4" })) });
    const events: Array<{ totalBytes: number | null; percent: number | null }> = [];
    await downloadVideoForOffline({ video, signal: new AbortController().signal, onProgress: (event) => events.push(event) }, harness.dependencies);
    expect(events.at(-1)).toMatchObject({ totalBytes: null, percent: null });
  });

  it("fails when the streamed byte count differs from metadata without a Content-Length header", async () => {
    const harness = createHarness({
      fetchImplementation: vi.fn().mockResolvedValue(responseFromChunks([new Uint8Array(5)], { "content-type": "video/mp4" })),
    });
    await expect(downloadVideoForOffline({ video, signal: new AbortController().signal }, harness.dependencies)).rejects.toMatchObject({
      code: "byte_size_mismatch",
    });
    expect(harness.dependencies.deleteCachedVideo).toHaveBeenCalledWith(VIDEO_ID_ONE);
  });

  it("returns a valid completed record without another fetch", async () => {
    const harness = createHarness();
    const completed: OfflineVideoRecord = {
      id: VIDEO_ID_ONE,
      title: video.title,
      contentType: "video/mp4",
      byteSize: 6,
      createdAt: video.created_at,
      status: "completed",
      downloadedBytes: 6,
      downloadedAt: video.created_at,
      cacheKey: getOfflineMediaPath(VIDEO_ID_ONE),
      lastErrorCode: null,
      lastErrorMessage: null,
      failedAt: null,
      lastWatchedAt: null,
      updatedAt: video.created_at,
    };
    harness.records.set(VIDEO_ID_ONE, completed);
    harness.dependencies.validateCachedVideo = vi.fn().mockResolvedValue({ valid: true, byteSize: 6 });
    const result = await downloadVideoForOffline({ video, signal: new AbortController().signal }, harness.dependencies);
    expect(result).toBe(completed);
    expect(harness.dependencies.fetchImplementation).not.toHaveBeenCalled();
  });

  it.each([
    [new Response("error", { status: 500 }), "http_error"],
    [new Response("missing", { status: 404 }), "http_error"],
    [new Response(null, { status: 200, headers: { "content-type": "video/mp4", "content-length": "6" } }), "response_body_missing"],
    [videoResponse(6, "text/html"), "unsupported_content_type"],
    [responseFromChunks([new Uint8Array(6)], { "content-type": "video/mp4", "content-length": "bad" }), "content_length_mismatch"],
    [responseFromChunks([new Uint8Array(6)], { "content-type": "video/mp4", "content-length": "5" }), "content_length_mismatch"],
    [responseFromChunks([new Uint8Array(5)], { "content-type": "video/mp4", "content-length": "5" }), "content_length_mismatch"],
  ])("fails safely for invalid response (%s)", async (response, code) => {
    const harness = createHarness({ fetchImplementation: vi.fn().mockResolvedValue(response) });
    await expect(downloadVideoForOffline({ video, signal: new AbortController().signal }, harness.dependencies)).rejects.toMatchObject({ code });
    expect(harness.records.get(VIDEO_ID_ONE)).toMatchObject({ status: "failed", lastErrorCode: code });
    expect(harness.cache.has(VIDEO_ID_ONE)).toBe(false);
  });

  it("cleans cache and fails safely for quota pre-check, cache write, validation, metadata and abort failures", async () => {
    const quota = createHarness({ hasEstimatedSpaceForDownload: vi.fn().mockReturnValue(false) });
    await expect(downloadVideoForOffline({ video, signal: new AbortController().signal }, quota.dependencies)).rejects.toMatchObject({ code: "storage_quota_exceeded" });

    const write = createHarness({ putCachedVideoOwnedResponse: vi.fn().mockRejectedValue(new DOMException("quota", "QuotaExceededError")) });
    await expect(downloadVideoForOffline({ video, signal: new AbortController().signal }, write.dependencies)).rejects.toMatchObject({ code: "storage_quota_exceeded" });

    const validation = createHarness({ validateCachedVideo: vi.fn().mockResolvedValue({ valid: false, reason: "size_mismatch" }) });
    await expect(downloadVideoForOffline({ video, signal: new AbortController().signal }, validation.dependencies)).rejects.toMatchObject({ code: "cache_validation_failed" });
    expect(validation.dependencies.deleteCachedVideo).toHaveBeenCalled();

    const transformFailure = createHarness({
      fetchImplementation: vi.fn().mockResolvedValue(
        new Response(
          new ReadableStream<Uint8Array>({
            start(controller) {
              controller.error(new TypeError("stream failed"));
            },
          }),
          { status: 200, headers: { "content-type": "video/mp4", "content-length": "6" } },
        ),
      ),
    });
    await expect(downloadVideoForOffline({ video, signal: new AbortController().signal }, transformFailure.dependencies)).rejects.toMatchObject({
      code: "network_error",
    });
    expect(transformFailure.dependencies.deleteCachedVideo).toHaveBeenCalledWith(VIDEO_ID_ONE);

    const metadata = createHarness();
    const baseUpdate = metadata.dependencies.updateOfflineVideo;
    metadata.dependencies.updateOfflineVideo = vi.fn(async (id, patch) => {
      if (typeof patch !== "function" && patch.status === "completed") return undefined;
      return baseUpdate(id, patch);
    });
    await expect(downloadVideoForOffline({ video, signal: new AbortController().signal }, metadata.dependencies)).rejects.toMatchObject({
      code: "unknown_error",
    });
    expect(metadata.dependencies.deleteCachedVideo).toHaveBeenCalledWith(VIDEO_ID_ONE);

    const controller = new AbortController();
    controller.abort();
    const aborted = createHarness({ fetchImplementation: vi.fn().mockRejectedValue(new DOMException("abort", "AbortError")) });
    await expect(downloadVideoForOffline({ video, signal: controller.signal }, aborted.dependencies)).rejects.toMatchObject({ code: "download_aborted" });
  });

  it("aborts the transformed stream without completing metadata", async () => {
    const controller = new AbortController();
    const harness = createHarness({
      fetchImplementation: vi.fn().mockImplementation(async () => {
        controller.abort();
        return responseFromChunks([new Uint8Array(6)]);
      }),
    });
    await expect(downloadVideoForOffline({ video, signal: controller.signal }, harness.dependencies)).rejects.toMatchObject({ code: "download_aborted" });
    expect(harness.records.get(VIDEO_ID_ONE)).toMatchObject({ status: "failed", lastErrorCode: "download_aborted" });
    expect(harness.cache.has(VIDEO_ID_ONE)).toBe(false);
  });
});

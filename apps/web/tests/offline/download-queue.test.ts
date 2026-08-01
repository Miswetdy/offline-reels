import { describe, expect, it, vi } from "vitest";

import { OfflineDownloadQueue } from "../../lib/offline/download-queue";
import { OfflineStorageError } from "../../lib/offline/errors";
import type { OfflineVideoPatch, OfflineVideoRecord } from "../../lib/offline/types";
import { VIDEO_ID_ONE, VIDEO_ID_TWO } from "./test-helpers";

const videoOne = { id: VIDEO_ID_ONE, title: "One", content_type: "video/mp4", byte_size: 10, created_at: "2026-07-22T12:00:00.000Z" };
const videoTwo = { id: VIDEO_ID_TWO, title: "Two", content_type: "video/mp4", byte_size: 20, created_at: "2026-07-22T12:00:01.000Z" };

function makeRecord(video: typeof videoOne, status: OfflineVideoRecord["status"] = "queued"): OfflineVideoRecord {
  return {
    id: video.id,
    title: video.title,
    contentType: "video/mp4",
    byteSize: video.byte_size,
    createdAt: video.created_at,
    status,
    downloadedBytes: status === "completed" ? video.byte_size : 0,
    downloadedAt: status === "completed" ? video.created_at : null,
    cacheKey: status === "completed" ? `/offline-media/${video.id}` : null,
    lastErrorCode: null,
    lastErrorMessage: null,
    failedAt: null,
    lastWatchedAt: null,
    updatedAt: video.created_at,
  };
}

function createQueueHarness(options: { online?: boolean; failFirst?: "network_error" | "storage_quota_exceeded" } = {}) {
  const records = new Map<string, OfflineVideoRecord>();
  const subscribers = new Set<() => void>();
  const downloads: string[] = [];
  const listRecords = vi.fn(async () => [...records.values()]);
  const clearLibrary = vi.fn(async () => {
    records.clear();
  });
  let online = options.online ?? true;
  let remainingFailure = options.failFirst;
  const update = vi.fn(async (id: string, updater: OfflineVideoPatch | ((record: OfflineVideoRecord) => OfflineVideoPatch)) => {
    const existing = records.get(id);
    if (!existing) return undefined;
    const patch = typeof updater === "function" ? updater(existing) : updater;
    const next = { ...existing, ...patch, updatedAt: "2026-07-22T12:01:00.000Z" };
    records.set(id, next);
    return next;
  });
  const downloader = vi.fn(async ({ video, signal, onProgress }: { video: typeof videoOne; signal: AbortSignal; onProgress?: (progress: never) => void }) => {
    downloads.push(video.id);
    if (signal.aborted) throw new DOMException("abort", "AbortError");
    if (remainingFailure) {
      const code = remainingFailure;
      remainingFailure = undefined;
      await update(video.id, { status: "failed", lastErrorCode: code, failedAt: video.created_at });
      throw new OfflineStorageError(code);
    }
    onProgress?.({ videoId: video.id, downloadedBytes: video.byte_size, totalBytes: video.byte_size, percent: 100 } as never);
    const completed = await update(video.id, {
      status: "completed",
      downloadedBytes: video.byte_size,
      downloadedAt: video.created_at,
      cacheKey: `/offline-media/${video.id}`,
    });
    return completed!;
  });
  const queue = new OfflineDownloadQueue({
    downloadVideoForOffline: downloader as never,
    reconcileOfflineLibrary: vi.fn().mockResolvedValue({}),
    getOfflineVideo: vi.fn(async (id: string) => records.get(id)),
    listOfflineVideos: listRecords,
    putOfflineVideo: vi.fn(async (record: OfflineVideoRecord) => void records.set(record.id, record)),
    updateOfflineVideo: update,
    deleteOfflineVideo: vi.fn(async (id: string) => {
      records.delete(id);
    }),
    calculateCompletedLibrarySize: vi.fn(async () => [...records.values()].filter((record) => record.status === "completed").reduce((total, record) => total + record.byteSize, 0)),
    clearOfflineLibrary: clearLibrary,
    isOnline: () => online,
    addNetworkListener: (_event, listener) => {
      subscribers.add(listener);
      return () => subscribers.delete(listener);
    },
  });
  return { queue, records, downloads, downloader, clearLibrary, listRecords, setOnline: (value: boolean) => { online = value; subscribers.forEach((listener) => listener()); } };
}

describe("offline download queue", () => {
  it("runs queued videos sequentially with one pump and one active job", async () => {
    const harness = createQueueHarness();
    await harness.queue.enqueueMany([videoOne, videoTwo]);
    const first = harness.queue.start();
    const second = harness.queue.start();
    await Promise.all([first, second]);

    expect(harness.downloads).toEqual([VIDEO_ID_ONE, VIDEO_ID_TWO]);
    expect(harness.downloader).toHaveBeenCalledTimes(2);
    expect(harness.queue.getSnapshot()).toMatchObject({ activeVideoId: null, queuedCount: 0, completedCount: 2, paused: false });
  });

  it("rejects duplicate and completed enqueue, requires explicit retry for failures, and supports removal", async () => {
    const harness = createQueueHarness();
    expect(await harness.queue.enqueue(videoOne)).toBe(true);
    expect(await harness.queue.enqueue(videoOne)).toBe(false);
    expect(await harness.queue.removeQueued(videoOne.id)).toBe(true);
    expect(await harness.queue.enqueue(videoOne)).toBe(true);
    await harness.queue.start();
    expect(await harness.queue.enqueue(videoOne)).toBe(false);

    await harness.queue.enqueue(videoTwo);
    harness.records.set(VIDEO_ID_TWO, makeRecord(videoTwo, "failed"));
    expect(await harness.queue.enqueue(videoTwo)).toBe(false);
    expect(await harness.queue.retry(videoTwo.id)).toBe(true);
    expect(harness.records.get(VIDEO_ID_TWO)?.status).toBe("queued");
  });

  it("starts a retried failed record without requiring a separate continue action", async () => {
    const harness = createQueueHarness();
    harness.records.set(VIDEO_ID_ONE, makeRecord(videoOne, "failed"));

    expect(await harness.queue.retry(VIDEO_ID_ONE)).toBe(true);
    await harness.queue.start();

    expect(harness.downloads).toEqual([VIDEO_ID_ONE]);
    expect(harness.records.get(VIDEO_ID_ONE)?.status).toBe("completed");
  });

  it("continues after ordinary failure but pauses after quota failure", async () => {
    const ordinary = createQueueHarness({ failFirst: "network_error" });
    await ordinary.queue.enqueueMany([videoOne, videoTwo]);
    await ordinary.queue.start();
    expect(ordinary.downloads).toEqual([VIDEO_ID_ONE, VIDEO_ID_TWO]);
    expect(ordinary.records.get(VIDEO_ID_ONE)?.status).toBe("failed");
    expect(ordinary.records.get(VIDEO_ID_TWO)?.status).toBe("completed");

    const quota = createQueueHarness({ failFirst: "storage_quota_exceeded" });
    await quota.queue.enqueueMany([videoOne, videoTwo]);
    await quota.queue.start();
    expect(quota.downloads).toEqual([VIDEO_ID_ONE]);
    expect(quota.queue.getSnapshot()).toMatchObject({ paused: true, queuedCount: 1, currentErrorCode: "storage_quota_exceeded" });
  });

  it("does not start while offline, observes subscriptions, and does not auto-start after online", async () => {
    const harness = createQueueHarness({ online: false });
    const listener = vi.fn();
    const unsubscribe = harness.queue.subscribe(listener);
    await harness.queue.enqueue(videoOne);
    await harness.queue.start();
    expect(harness.downloads).toEqual([]);
    expect(harness.queue.getSnapshot()).toMatchObject({ paused: true, online: false, queuedCount: 1 });

    harness.setOnline(true);
    expect(harness.downloads).toEqual([]);
    expect(listener).toHaveBeenCalled();
    unsubscribe();
    await harness.queue.start();
    expect(harness.downloads).toEqual([VIDEO_ID_ONE]);
  });

  it("aborts the active controller, pauses the queue, and leaves the next item queued", async () => {
    let rejectDownload: ((reason?: unknown) => void) | undefined;
    const harness = createQueueHarness();
    harness.downloader.mockImplementationOnce(({ signal }: { signal: AbortSignal }) =>
      new Promise((_, reject) => {
        rejectDownload = reject;
        signal.addEventListener("abort", () => reject(new DOMException("abort", "AbortError")), { once: true });
      }),
    );
    await harness.queue.enqueueMany([videoOne, videoTwo]);
    const start = harness.queue.start();
    await vi.waitFor(() => expect(harness.queue.getSnapshot().activeVideoId).toBe(VIDEO_ID_ONE));
    harness.queue.abortActive();
    rejectDownload?.(new DOMException("abort", "AbortError"));
    await start;

    expect(harness.queue.getSnapshot()).toMatchObject({ paused: true, activeVideoId: null, queuedCount: 2, currentErrorCode: "download_aborted" });
  });

  it("downloads a deduplicated catalog batch sequentially and exposes monotonic aggregate progress", async () => {
    const harness = createQueueHarness();

    await expect(harness.queue.enqueueCatalogAndStart([videoOne, videoOne, videoTwo])).resolves.toBe(2);
    await vi.waitFor(() => expect(harness.queue.getSnapshot().batchProgress).toMatchObject({ totalBytes: 30, completedBytes: 30, displayedBytes: 30, state: "completed" }));
    expect(harness.downloads).toEqual([VIDEO_ID_ONE, VIDEO_ID_TWO]);
  });

  it("requeues failed catalog records but keeps valid completed records untouched", async () => {
    const harness = createQueueHarness();
    harness.records.set(VIDEO_ID_ONE, makeRecord(videoOne, "completed"));
    harness.records.set(VIDEO_ID_TWO, makeRecord(videoTwo, "failed"));

    await expect(harness.queue.enqueueCatalogAndStart([videoOne, videoTwo])).resolves.toBe(1);
    await vi.waitFor(() => expect(harness.records.get(VIDEO_ID_TWO)?.status).toBe("completed"));
    expect(harness.downloads).toEqual([VIDEO_ID_TWO]);
  });

  it("cancels an active batch and removes its remaining queued work", async () => {
    const harness = createQueueHarness();
    harness.downloader.mockImplementationOnce(({ video, signal }: { video: typeof videoOne; signal: AbortSignal }) =>
      new Promise((_, reject) => {
        signal.addEventListener("abort", () => {
          void harness.records.set(video.id, makeRecord(video, "failed"));
          reject(new DOMException("abort", "AbortError"));
        }, { once: true });
      }),
    );

    await harness.queue.enqueueCatalogAndStart([videoOne, videoTwo]);
    await vi.waitFor(() => expect(harness.queue.getSnapshot().activeVideoId).toBe(VIDEO_ID_ONE));
    await harness.queue.cancelBatch();

    expect(harness.records.get(VIDEO_ID_ONE)?.status).toBe("failed");
    expect(harness.records.has(VIDEO_ID_TWO)).toBe(false);
    expect(harness.queue.getSnapshot().batchProgress?.state).toBe("failed");
  });

  it("waits for an aborted active write before clearing so a late completion cannot repopulate the library", async () => {
    let finishDownload!: () => void;
    const harness = createQueueHarness();
    harness.downloader.mockImplementationOnce(({ video, onProgress }: { video: typeof videoOne; onProgress?: (progress: never) => void }) =>
      new Promise((resolve) => {
        finishDownload = () => {
          onProgress?.({ videoId: video.id, downloadedBytes: video.byte_size, totalBytes: video.byte_size, percent: 100 } as never);
          const completed = makeRecord(video, "completed");
          harness.records.set(video.id, completed);
          resolve(completed);
        };
      }),
    );
    await harness.queue.enqueue(videoOne);
    const start = harness.queue.start();
    await vi.waitFor(() => expect(harness.queue.getSnapshot().activeVideoId).toBe(VIDEO_ID_ONE));

    const clear = harness.queue.cancelAndClear();
    expect(harness.clearLibrary).not.toHaveBeenCalled();
    finishDownload();
    await Promise.all([start, clear]);

    expect(harness.clearLibrary).toHaveBeenCalledOnce();
    expect(harness.records.size).toBe(0);
    expect(harness.queue.getSnapshot()).toMatchObject({ clearing: false, queuedCount: 0, completedCount: 0, activeVideoId: null });
  });

  it("refreshes the observable snapshot after a partially failed clear and leaves clearing false", async () => {
    const clearError = new Error("metadata cleanup failed");
    const harness = createQueueHarness();
    harness.records.set(VIDEO_ID_ONE, makeRecord(videoOne, "completed"));
    await harness.queue.initialize();
    harness.clearLibrary.mockImplementationOnce(async () => {
      harness.records.delete(VIDEO_ID_ONE);
      throw clearError;
    });

    await expect(harness.queue.cancelAndClear()).rejects.toBe(clearError);

    expect(harness.clearLibrary).toHaveBeenCalledOnce();
    expect(harness.queue.getSnapshot()).toMatchObject({ records: [], completedCount: 0, clearing: false });
  });

  it("preserves the original clear error when the best-effort refresh also fails", async () => {
    const clearError = new Error("clear failed");
    const refreshError = new Error("refresh failed");
    const harness = createQueueHarness();
    await harness.queue.initialize();
    harness.clearLibrary.mockRejectedValueOnce(clearError);
    harness.listRecords.mockRejectedValueOnce(refreshError);

    await expect(harness.queue.cancelAndClear()).rejects.toBe(clearError);

    expect(harness.clearLibrary).toHaveBeenCalledOnce();
    expect(harness.listRecords).toHaveBeenCalledTimes(2);
    expect(harness.queue.getSnapshot().clearing).toBe(false);
  });
});

// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import "fake-indexeddb/auto";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OfflineDownloadControls } from "../../components/offline-download-controls";
import { getCachedVideo } from "../../lib/offline/media-cache";
import { getOfflineVideo, putOfflineVideo } from "../../lib/offline/repository";
import { installFakeCacheStorage, resetOfflineDatabase, VIDEO_ID_ONE } from "./test-helpers";

const video = {
  id: VIDEO_ID_ONE,
  title: "Flow video",
  content_type: "video/mp4",
  byte_size: 4,
  created_at: "2026-07-23T12:00:00.000Z",
};

beforeEach(async () => {
  installFakeCacheStorage();
  await resetOfflineDatabase();
  Object.defineProperty(window, "__offlineReelsDownloadQueueV1", { configurable: true, writable: true, value: undefined });
  Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
});

afterEach(async () => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  await resetOfflineDatabase();
  Reflect.deleteProperty(window, "__offlineReelsDownloadQueueV1");
  Reflect.deleteProperty(globalThis, "caches");
});

describe("offline download frontend flow", () => {
  it("starts a fresh click automatically and completes Cache Storage before IndexedDB", async () => {
    const fetchImplementation = vi.fn().mockResolvedValue(
      new Response(new Uint8Array([1, 2, 3, 4]), {
        status: 200,
        headers: { "content-type": "video/mp4", "content-length": "4" },
      }),
    );
    vi.stubGlobal("fetch", fetchImplementation);

    render(<OfflineDownloadControls videos={[video]} activeVideoId={video.id} />);
    const download = await screen.findByRole("button", { name: "Скачать текущий" });
    fireEvent.click(download);

    await waitFor(() => expect(fetchImplementation).toHaveBeenCalledOnce());
    await waitFor(() => expect(screen.getByText(/Офлайн: 1 видео/)).toBeInTheDocument());
    expect(fetchImplementation.mock.calls[0][0]).toBe(`http://localhost:8000/videos/${video.id}/stream`);
    expect(await getCachedVideo(video.id)).toBeDefined();
    await expect(getOfflineVideo(video.id)).resolves.toMatchObject({
      status: "completed",
      downloadedBytes: 4,
      cacheKey: `/offline-media/${video.id}`,
    });

    fireEvent.click(screen.getByRole("button", { name: "Скачать следующие 5" }));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetchImplementation).toHaveBeenCalledOnce();
  });

  it("retries a persisted failed record and starts the downloader without Continue", async () => {
    await putOfflineVideo({
      id: video.id,
      title: video.title,
      contentType: "video/mp4",
      byteSize: 4,
      createdAt: video.created_at,
      status: "failed",
      downloadedBytes: 0,
      downloadedAt: null,
      cacheKey: null,
      lastErrorCode: "network_error",
      lastErrorMessage: "safe message",
      failedAt: video.created_at,
      lastWatchedAt: null,
      updatedAt: video.created_at,
    });
    const fetchImplementation = vi.fn().mockResolvedValue(
      new Response(new Uint8Array([1, 2, 3, 4]), {
        status: 200,
        headers: { "content-type": "video/mp4", "content-length": "4" },
      }),
    );
    vi.stubGlobal("fetch", fetchImplementation);

    render(<OfflineDownloadControls videos={[video]} activeVideoId={video.id} />);
    fireEvent.click(await screen.findByRole("button", { name: "Повторить" }));

    await waitFor(() => expect(fetchImplementation).toHaveBeenCalledOnce());
    await expect(getOfflineVideo(video.id)).resolves.toMatchObject({ status: "completed", downloadedBytes: 4 });
  });

  it("cancels an active downloader and exposes an explicit retry", async () => {
    const fetchImplementation = vi.fn((_url: string, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true });
      }),
    );
    vi.stubGlobal("fetch", fetchImplementation);

    render(<OfflineDownloadControls videos={[video]} activeVideoId={video.id} />);
    fireEvent.click(await screen.findByRole("button", { name: "Скачать текущий" }));
    await waitFor(() => expect(fetchImplementation).toHaveBeenCalledOnce());
    fireEvent.click(await screen.findByRole("button", { name: "Отменить" }));

    expect(await screen.findByRole("button", { name: "Повторить" })).toBeInTheDocument();
    await expect(getOfflineVideo(video.id)).resolves.toMatchObject({ status: "failed", lastErrorCode: "download_aborted" });
  });
});

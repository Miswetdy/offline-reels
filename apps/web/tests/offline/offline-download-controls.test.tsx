// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OfflineDownloadControls } from "../../components/offline-download-controls";
import * as downloads from "../../hooks/use-offline-downloads";
import { VIDEO_ID_ONE, VIDEO_ID_TWO, VIDEO_ID_THREE } from "./test-helpers";

const videos = [
  { id: VIDEO_ID_ONE, title: "One", content_type: "video/mp4", byte_size: 10, created_at: "2026-07-22T12:00:00Z" },
  { id: VIDEO_ID_TWO, title: "Two", content_type: "video/mp4", byte_size: 20, created_at: "2026-07-22T12:00:01Z" },
  { id: VIDEO_ID_THREE, title: "Three", content_type: "video/mp4", byte_size: 30, created_at: "2026-07-22T12:00:02Z" },
];

function renderControls(overrides: Partial<ReturnType<typeof downloads.useOfflineDownloads>> = {}) {
  const api = {
    snapshot: {
      activeVideoId: null,
      paused: false,
      queuedCount: 0,
      completedCount: 0,
      completedBytes: 0,
      currentProgress: null,
      currentErrorCode: null,
      online: true,
      records: [],
    },
    enqueueAndStart: vi.fn().mockResolvedValue(true),
    enqueueManyAndStart: vi.fn().mockResolvedValue(2),
    retryAndStart: vi.fn().mockResolvedValue(true),
    continueDownloads: vi.fn(),
    abortActive: vi.fn(),
    ...overrides,
  };
  vi.spyOn(downloads, "useOfflineDownloads").mockReturnValue(api);
  render(<OfflineDownloadControls videos={videos} activeVideoId={VIDEO_ID_ONE} />);
  return api;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("OfflineDownloadControls", () => {
  it("enqueues the current video and only eligible following videos in a batch", () => {
    const api = renderControls({
      snapshot: {
        activeVideoId: null,
        paused: false,
        queuedCount: 1,
        completedCount: 1,
        completedBytes: 10,
        currentProgress: null,
        currentErrorCode: null,
        online: true,
        records: [
          { id: VIDEO_ID_TWO, status: "completed" },
          { id: VIDEO_ID_THREE, status: "queued" },
        ] as never,
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Скачать текущий" }));
    expect(api.enqueueAndStart).toHaveBeenCalledWith(videos[0]);
    fireEvent.click(screen.getByRole("button", { name: "Скачать следующие 5" }));
    expect(api.enqueueManyAndStart).toHaveBeenCalledWith([videos[0]]);
  });

  it("shows progress, cancel, paused queue resume and safe errors", () => {
    const api = renderControls({
      snapshot: {
        activeVideoId: VIDEO_ID_ONE,
        paused: true,
        queuedCount: 2,
        completedCount: 0,
        completedBytes: 0,
        currentProgress: { videoId: VIDEO_ID_ONE, downloadedBytes: 5, totalBytes: null, percent: null },
        currentErrorCode: "download_aborted",
        online: true,
        records: [{ id: VIDEO_ID_ONE, status: "downloading" }] as never,
      },
    });
    expect(screen.getByText("5 Б · загрузка…")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Загрузка отменена.");
    fireEvent.click(screen.getByRole("button", { name: "Отменить" }));
    fireEvent.click(screen.getByRole("button", { name: "Продолжить загрузку" }));
    expect(api.abortActive).toHaveBeenCalledOnce();
    expect(api.continueDownloads).toHaveBeenCalledOnce();
  });

  it("uses explicit retry for a failed active video and disables network actions offline", () => {
    const api = renderControls({
      snapshot: {
        activeVideoId: null,
        paused: true,
        queuedCount: 0,
        completedCount: 0,
        completedBytes: 0,
        currentProgress: null,
        currentErrorCode: null,
        online: false,
        records: [{ id: VIDEO_ID_ONE, status: "failed", lastErrorCode: "network_error" }] as never,
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
    expect(api.retryAndStart).toHaveBeenCalledWith(VIDEO_ID_ONE);
    expect(screen.getByText(/Нет подключения/)).toBeInTheDocument();
  });
});

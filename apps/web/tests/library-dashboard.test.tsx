// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  catalog: vi.fn(),
  estimate: vi.fn(),
  hasSpace: vi.fn(),
  enqueueCatalog: vi.fn(),
  cancelBatch: vi.fn(),
  cancelAndClear: vi.fn(),
  snapshot: null as unknown,
}));

vi.mock("../lib/api/videos", () => ({ getEntireVideoCatalog: mocks.catalog }));
vi.mock("../lib/offline/storage", () => ({
  getStorageEstimate: mocks.estimate,
  hasEstimatedSpaceForDownload: mocks.hasSpace,
}));
vi.mock("../hooks/use-offline-downloads", () => ({
  useOfflineDownloads: () => ({
    snapshot: mocks.snapshot,
    enqueueCatalogAndStart: mocks.enqueueCatalog,
    cancelBatch: mocks.cancelBatch,
    cancelAndClear: mocks.cancelAndClear,
  }),
}));

import { getStorageUsagePresentation, LibraryDashboard } from "../components/library-dashboard";

const video = { id: "00000000-0000-4000-8000-000000000001", title: "Hidden title", content_type: "video/mp4", byte_size: 10, created_at: "2026-08-01T00:00:00.000Z" };

function snapshot(overrides: Record<string, unknown> = {}) {
  return {
    activeVideoId: null,
    paused: true,
    queuedCount: 0,
    completedCount: 0,
    completedBytes: 0,
    currentProgress: null,
    currentErrorCode: null,
    online: true,
    initialized: true,
    clearing: false,
    batchProgress: null,
    records: [],
    ...overrides,
  };
}

function setNetworkOnline(online: boolean) {
  Object.defineProperty(navigator, "onLine", { configurable: true, value: online });
}

beforeEach(() => {
  mocks.catalog.mockResolvedValue([video]);
  mocks.estimate.mockResolvedValue({ usage: 0, quota: 100, available: 100, isAvailable: true });
  mocks.hasSpace.mockReturnValue(true);
  mocks.enqueueCatalog.mockResolvedValue(1);
  mocks.cancelAndClear.mockResolvedValue(undefined);
  mocks.snapshot = snapshot();
  setNetworkOnline(true);
  vi.stubGlobal("confirm", vi.fn(() => true));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("LibraryDashboard", () => {
  it("renders the clean canonical dashboard without video, catalog metadata, byte labels, or counters", async () => {
    render(<LibraryDashboard />);

    expect(await screen.findByRole("heading", { name: "Offline Reels" })).toBeInTheDocument();
    expect(screen.getByText("Онлайн")).toBeInTheDocument();
    expect(screen.getByText("Хранилище не используется — 0%")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Загрузить Reels" })).toBeEnabled();
    expect(screen.queryByText("Hidden title")).not.toBeInTheDocument();
    expect(document.querySelector("video")).not.toBeInTheDocument();
    expect(screen.queryByText(/bytes|МБ|ГБ|видео/i)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Главная" })).toHaveAttribute("href", "/");
  });

  it("starts every eligible catalog item through the singleton batch queue", async () => {
    const second = { ...video, id: "00000000-0000-4000-8000-000000000002" };
    mocks.catalog.mockResolvedValueOnce([video, second]);
    render(<LibraryDashboard />);

    fireEvent.click(await screen.findByRole("button", { name: "Загрузить Reels" }));
    await waitFor(() => expect(mocks.enqueueCatalog).toHaveBeenCalledWith([video, second]));
  });

  it("shows a safe action error when starting a batch fails and clears it after a successful retry", async () => {
    mocks.enqueueCatalog.mockRejectedValueOnce(new Error("indexeddb failed"));
    render(<LibraryDashboard />);

    const start = await screen.findByRole("button", { name: "Загрузить Reels" });
    fireEvent.click(start);

    const alert = await screen.findByText("Не удалось начать загрузку Reels. Попробуйте ещё раз.");
    expect(alert).toHaveAttribute("role", "alert");
    expect(screen.queryByText("indexeddb failed")).not.toBeInTheDocument();

    mocks.enqueueCatalog.mockResolvedValueOnce(1);
    await waitFor(() => expect(start).toBeEnabled());
    fireEvent.click(start);

    await waitFor(() => expect(screen.queryByText("Не удалось начать загрузку Reels. Попробуйте ещё раз.")).not.toBeInTheDocument());
  });

  it("disables download offline and when every catalog item is completed", async () => {
    mocks.snapshot = snapshot({ online: false });
    render(<LibraryDashboard />);
    expect(await screen.findByRole("button", { name: "Загрузить Reels" })).toBeDisabled();
    cleanup();

    mocks.snapshot = snapshot({ records: [{ id: video.id, status: "completed" }] });
    render(<LibraryDashboard />);
    expect(await screen.findByRole("button", { name: "Загрузить Reels" })).toBeDisabled();
  });

  it("does not request the catalog or show a catalog error while initially offline", async () => {
    setNetworkOnline(false);
    render(<LibraryDashboard />);
    await act(async () => Promise.resolve());

    expect(mocks.catalog).not.toHaveBeenCalled();
    expect(screen.getByText("Нет подключения")).toBeInTheDocument();
    expect(screen.queryByText("Не удалось загрузить каталог Reels.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Повторить" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Загрузить Reels" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Очистить библиотеку" })).toBeEnabled();
  });

  it("aborts and invalidates a pending catalog request when the network goes offline", async () => {
    let rejectCatalog!: (reason?: unknown) => void;
    let signal!: AbortSignal;
    mocks.catalog.mockImplementationOnce(({ signal: requestSignal }: { signal: AbortSignal }) => new Promise((_, reject) => {
      signal = requestSignal;
      rejectCatalog = reject;
    }));
    render(<LibraryDashboard />);
    await waitFor(() => expect(mocks.catalog).toHaveBeenCalledOnce());

    await act(async () => {
      setNetworkOnline(false);
      window.dispatchEvent(new Event("offline"));
    });
    expect(signal.aborted).toBe(true);

    await act(async () => {
      rejectCatalog(new Error("offline request failed"));
      await Promise.resolve();
    });
    expect(screen.queryByText("Не удалось загрузить каталог Reels.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Повторить" })).not.toBeInTheDocument();
  });

  it("loads the catalog automatically after an offline-to-online transition", async () => {
    setNetworkOnline(false);
    render(<LibraryDashboard />);
    await act(async () => Promise.resolve());
    expect(mocks.catalog).not.toHaveBeenCalled();

    await act(async () => {
      setNetworkOnline(true);
      window.dispatchEvent(new Event("online"));
    });

    await waitFor(() => expect(mocks.catalog).toHaveBeenCalledOnce());
    expect(await screen.findByRole("button", { name: "Загрузить Reels" })).toBeEnabled();
  });

  it("keeps the catalog error and retry action for a real online failure", async () => {
    mocks.catalog.mockRejectedValueOnce(new Error("server unavailable"));
    render(<LibraryDashboard />);

    expect(await screen.findByText("Не удалось загрузить каталог Reels.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Повторить" })).toBeEnabled();
  });

  it("shows monotonic batch progress only as a percentage and can cancel", async () => {
    mocks.snapshot = snapshot({
      activeVideoId: video.id,
      batchProgress: { totalBytes: 100, completedBytes: 20, displayedBytes: 42, state: "active" },
    });
    render(<LibraryDashboard />);

    expect(await screen.findByText("Загрузка Reels — 42%")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Загрузка Reels" })).toHaveAttribute("aria-valuenow", "42");
    fireEvent.click(screen.getByRole("button", { name: "Отменить загрузку" }));
    expect(mocks.cancelBatch).toHaveBeenCalledOnce();
  });

  it("reports quota exhaustion without deriving it from rounded display percentage", async () => {
    mocks.hasSpace.mockReturnValue(false);
    render(<LibraryDashboard />);

    expect(await screen.findByText("Память уже заполнена. Больше Reels скачать нельзя.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Загрузить Reels" })).toBeDisabled();
  });

  it("uses the exact confirmation before cancel-and-clear", async () => {
    render(<LibraryDashboard />);
    fireEvent.click(await screen.findByRole("button", { name: "Очистить библиотеку" }));

    expect(window.confirm).toHaveBeenCalledWith("Вы точно хотите удалить все скачанные Reels?");
    await waitFor(() => expect(mocks.cancelAndClear).toHaveBeenCalledOnce());
  });

  it("shows a safe action error when clearing fails and restores the clear action", async () => {
    mocks.cancelAndClear.mockRejectedValueOnce(new Error("cache cleanup failed"));
    render(<LibraryDashboard />);

    const clear = await screen.findByRole("button", { name: "Очистить библиотеку" });
    fireEvent.click(clear);

    const alert = await screen.findByText("Не удалось полностью очистить библиотеку. Попробуйте ещё раз.");
    expect(alert).toHaveAttribute("role", "alert");
    expect(screen.queryByText("cache cleanup failed")).not.toBeInTheDocument();
    await waitFor(() => expect(clear).toBeEnabled());
  });

  it("disables retry whenever the shared canStart condition forbids starting", async () => {
    mocks.snapshot = snapshot({ records: [{ id: video.id, status: "failed" }] });
    mocks.hasSpace.mockReturnValue(false);
    render(<LibraryDashboard />);

    expect(await screen.findByRole("button", { name: "Повторить" })).toBeDisabled();
  });
});

describe("storage usage presentation", () => {
  it("handles zero, sub-percent, ordinary, and unavailable estimates without exposing bytes", () => {
    expect(getStorageUsagePresentation({ usage: 0, quota: 100, available: 100, isAvailable: true })).toEqual({ label: "Хранилище не используется — 0%", percent: 0 });
    expect(getStorageUsagePresentation({ usage: 0.5, quota: 100, available: 99.5, isAvailable: true })).toEqual({ label: "Хранилище заполнено менее чем на 1%", percent: 0.5 });
    expect(getStorageUsagePresentation({ usage: 37, quota: 100, available: 63, isAvailable: true })).toEqual({ label: "Хранилище заполнено на 37%", percent: 37 });
    expect(getStorageUsagePresentation({ usage: null, quota: null, available: null, isAvailable: false })).toEqual({ label: "Не удалось определить заполненность хранилища", percent: null });
  });
});

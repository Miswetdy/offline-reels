// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  reconcile: vi.fn(), listCompleted: vi.fn(), estimate: vi.fn(), persisted: vi.fn(), deleteVideo: vi.fn(), clearLibrary: vi.fn(),
}));

vi.mock("../../lib/offline/reconciliation", () => ({ reconcileOfflineLibrary: mocks.reconcile }));
vi.mock("../../lib/offline/repository", () => ({ listCompletedOfflineVideos: mocks.listCompleted }));
vi.mock("../../lib/offline/storage", () => ({
  getStorageEstimate: mocks.estimate,
  getPersistentStorageStatus: mocks.persisted,
}));
vi.mock("../../lib/offline/library-management", () => ({
  deleteOfflineLibraryVideo: mocks.deleteVideo,
  clearOfflineLibrary: mocks.clearLibrary,
}));
vi.mock("../../lib/offline/media-cache", () => ({
  getMediaCacheKey: (videoId: string) => `/offline-media/${videoId}`,
}));
import { OfflineVideoList } from "../../components/offline-video-list";
import { VIDEO_ID_ONE, VIDEO_ID_TWO } from "./test-helpers";

const base = (id: string, byteSize: number, title: string) => ({
  id, title, contentType: "video/mp4", byteSize, createdAt: "2026-07-23T12:00:00.000Z",
  status: "completed" as const, downloadedBytes: byteSize, downloadedAt: "2026-07-23T13:00:00.000Z",
  cacheKey: `/offline-media/${id}`, lastErrorCode: null, lastErrorMessage: null,
  failedAt: null, lastWatchedAt: null, updatedAt: "2026-07-23T13:00:00.000Z",
});

class MockIntersectionObserver {
  readonly observe = vi.fn(); readonly disconnect = vi.fn();
  constructor(private readonly callback: IntersectionObserverCallback) {}
  trigger(target: Element) { this.callback([{ target, isIntersecting: true, intersectionRatio: 1 } as IntersectionObserverEntry], this as unknown as IntersectionObserver); }
}

let records = [base(VIDEO_ID_ONE, 4, "First"), base(VIDEO_ID_TWO, 6, "Second")];

beforeEach(() => {
  records = [base(VIDEO_ID_ONE, 4, "First"), base(VIDEO_ID_TWO, 6, "Second")];
  mocks.reconcile.mockResolvedValue({ errors: [] });
  mocks.listCompleted.mockImplementation(async () => records);
  mocks.estimate.mockResolvedValue({ usage: 100, quota: 1000, available: 900, isAvailable: true });
  mocks.persisted.mockResolvedValue(null);
  mocks.deleteVideo.mockImplementation(async (id: string) => { records = records.filter((record) => record.id !== id); });
  mocks.clearLibrary.mockImplementation(async () => { records = []; });
  window.history.replaceState({}, "", "/offline");
  vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
  vi.stubGlobal("confirm", vi.fn(() => true));
  const serviceWorker = new EventTarget();
  Object.defineProperties(serviceWorker, {
    controller: { configurable: true, value: {} },
    ready: { configurable: true, value: Promise.resolve({}) },
  });
  Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: serviceWorker });
  vi.spyOn(globalThis, "fetch");
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, "serviceWorker");
});

describe("OfflineVideoList management", () => {
  it("deletes an item, blocks repeat action, updates summary, and keeps Blob APIs unused", async () => {
    let finish!: () => void;
    mocks.deleteVideo.mockImplementationOnce(() => new Promise<void>((resolve) => { finish = () => { records = [records[1]]; resolve(); }; }));
    render(<OfflineVideoList />);
    await screen.findByText("First");
    const deleteButtons = screen.getAllByRole("button", { name: "Удалить с устройства" });
    fireEvent.click(deleteButtons[0]);
    expect(await screen.findByRole("button", { name: "Удаление…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Удалить с устройства" })).toBeDisabled();
    finish();
    expect(screen.queryByText("Загрузка офлайн-библиотеки…")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("First")).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getByLabelText("Offline library summary")).toHaveTextContent("Офлайн: 1 видео · 6 Б"));
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("shows empty state after deleting the last item and reports controlled errors", async () => {
    records = [base(VIDEO_ID_ONE, 4, "First")];
    mocks.deleteVideo.mockRejectedValueOnce(new Error("storage failure"));
    render(<OfflineVideoList />);
    await screen.findByText("First");
    fireEvent.click(screen.getByRole("button", { name: "Удалить с устройства" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("local video library");
    mocks.deleteVideo.mockImplementationOnce(async () => { records = []; });
    fireEvent.click(screen.getByRole("button", { name: "Удалить с устройства" }));
    expect(await screen.findByText("Офлайн-библиотека пуста")).toBeInTheDocument();
  });

  it("does nothing when clear confirmation is cancelled", async () => {
    vi.mocked(window.confirm).mockReturnValue(false);
    render(<OfflineVideoList />);
    await screen.findByText("First");
    fireEvent.click(screen.getByRole("button", { name: "Очистить офлайн-библиотеку" }));
    expect(mocks.clearLibrary).not.toHaveBeenCalled();
    expect(screen.getByText("First")).toBeInTheDocument();
  });

  it("clears the library, blocks repeat action, and never fetches backend", async () => {
    let finish!: () => void;
    mocks.clearLibrary.mockImplementationOnce(() => new Promise<void>((resolve) => { finish = () => { records = []; resolve(); }; }));
    render(<OfflineVideoList />);
    await screen.findByText("First");
    fireEvent.click(screen.getByRole("button", { name: "Очистить офлайн-библиотеку" }));
    expect(await screen.findByRole("button", { name: "Очистка…" })).toBeDisabled();
    finish();
    expect(await screen.findByText("Офлайн-библиотека пуста")).toBeInTheDocument();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("uses synthetic Service Worker media URLs", async () => {
    render(<OfflineVideoList />);

    const first = await screen.findByLabelText("First");
    const second = screen.getByLabelText("Second");
    const firstVideo = first.querySelector("video");
    await waitFor(() => expect(firstVideo).toHaveAttribute("src", `/offline-media/${VIDEO_ID_ONE}`));
    expect(second.querySelector("video")).toHaveAttribute("src", `/offline-media/${VIDEO_ID_TWO}`);
    expect(firstVideo).not.toHaveAttribute("controls");
    expect(firstVideo).toHaveAttribute("loop");
    expect(document.querySelector('[data-testid^="reels-gesture-"]')).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Turn sound on" })).not.toBeInTheDocument();
    expect(screen.getByTestId("app-bottom-navigation")).toHaveClass("app-bottom-navigation--floating");
    expect(screen.getByTestId("reels-bottom-glass-backdrop")).toHaveClass("reels-bottom-glass-backdrop");
    expect(screen.getByRole("link", { name: "Офлайн-библиотека" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Главная и загрузка" })).toHaveAttribute("href", "/videos");
    expect(screen.queryByRole("link", { name: "К онлайн-ленте" })).not.toBeInTheDocument();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("keeps storage diagnostics useful when persisted() is unavailable", async () => {
    mocks.persisted.mockResolvedValueOnce(null);
    render(<OfflineVideoList />);

    expect(await screen.findByLabelText("Offline library summary")).toHaveTextContent("Защита хранилища: недоступно");
  });

  it("shows a controlled state until a Service Worker controls the page", async () => {
    Object.defineProperty(navigator.serviceWorker, "controller", { configurable: true, value: null });
    render(<OfflineVideoList />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Офлайн-воспроизведение станет доступно после активации Service Worker.");
    expect(screen.queryByLabelText("Video feed")).not.toBeInTheDocument();
  });

  it("updates from waiting to controlled after controllerchange without reloading", async () => {
    Object.defineProperty(navigator.serviceWorker, "controller", { configurable: true, value: null });
    render(<OfflineVideoList />);
    expect(await screen.findByRole("alert")).toHaveTextContent("после активации Service Worker");

    Object.defineProperty(navigator.serviceWorker, "controller", { configurable: true, value: {} });
    await act(async () => {
      navigator.serviceWorker.dispatchEvent(new Event("controllerchange"));
    });

    expect(await screen.findByLabelText("Video feed")).toBeInTheDocument();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("shows a controlled state when Service Worker APIs are unavailable", async () => {
    Reflect.deleteProperty(navigator, "serviceWorker");
    render(<OfflineVideoList />);

    expect(await screen.findByRole("alert")).toHaveTextContent("не поддерживает Service Worker");
    expect(screen.queryByLabelText("Video feed")).not.toBeInTheDocument();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("shows a controlled storage error instead of a catalog when reconciliation cannot read Cache Storage", async () => {
    mocks.reconcile.mockResolvedValueOnce({ errors: [{ code: "browser_storage_unavailable" }], storageUnavailable: true });
    render(<OfflineVideoList />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Browser storage is unavailable");
    expect(screen.queryByLabelText("Video feed")).not.toBeInTheDocument();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  reconcile: vi.fn(),
  listCompleted: vi.fn(),
}));

vi.mock("../../lib/offline/reconciliation", () => ({ reconcileOfflineLibrary: mocks.reconcile }));
vi.mock("../../lib/offline/repository", () => ({ listCompletedOfflineVideos: mocks.listCompleted }));
vi.mock("../../lib/offline/media-cache", () => ({ getMediaCacheKey: (videoId: string) => `/offline-media/${videoId}` }));

import { OfflineVideoList } from "../../components/offline-video-list";
import { VIDEO_ID_ONE } from "./test-helpers";

const record = {
  id: VIDEO_ID_ONE,
  title: "Technical title",
  contentType: "video/mp4",
  byteSize: 4,
  createdAt: "2026-07-23T12:00:00.000Z",
  status: "completed" as const,
  downloadedBytes: 4,
  downloadedAt: "2026-07-23T13:00:00.000Z",
  cacheKey: `/offline-media/${VIDEO_ID_ONE}`,
  lastErrorCode: null,
  lastErrorMessage: null,
  failedAt: null,
  lastWatchedAt: null,
  updatedAt: "2026-07-23T13:00:00.000Z",
};

class MockIntersectionObserver {
  readonly observe = vi.fn();
  readonly disconnect = vi.fn();
  constructor(private readonly callback: IntersectionObserverCallback) {}
  trigger(target: Element) {
    this.callback([{ target, isIntersecting: true, intersectionRatio: 1 } as IntersectionObserverEntry], this as unknown as IntersectionObserver);
  }
}

beforeEach(() => {
  mocks.reconcile.mockResolvedValue({ errors: [], storageUnavailable: false });
  mocks.listCompleted.mockResolvedValue([record]);
  vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => undefined);
  const serviceWorker = new EventTarget();
  Object.defineProperties(serviceWorker, {
    controller: { configurable: true, value: {} },
    ready: { configurable: true, value: Promise.resolve({}) },
  });
  Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: serviceWorker });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, "serviceWorker");
});

describe("OfflineVideoList", () => {
  it("renders only the Reels surface and hides technical record presentation", async () => {
    render(<OfflineVideoList />);

    const reel = await screen.findByLabelText("Technical title");
    await waitFor(() => expect(reel.querySelector("video")).toHaveAttribute("src", `/offline-media/${VIDEO_ID_ONE}`));
    expect(reel.querySelector("video")).toHaveAttribute("loop");
    expect(screen.queryByText("Technical title")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Offline library summary")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Удалить/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Рилсы" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Главная" })).toHaveAttribute("href", "/");
  });

  it("shows the clean empty state with a canonical home link", async () => {
    mocks.listCompleted.mockResolvedValueOnce([]);
    render(<OfflineVideoList />);

    expect(await screen.findByText("Пока нет скачанных Reels")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Перейти на главную" })).toHaveAttribute("href", "/");
  });

  it("waits for Service Worker control without touching the backend", async () => {
    Object.defineProperty(navigator.serviceWorker, "controller", { configurable: true, value: null });
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<OfflineVideoList />);

    expect(await screen.findByRole("alert")).toHaveTextContent("после активации Service Worker");
    Object.defineProperty(navigator.serviceWorker, "controller", { configurable: true, value: {} });
    await act(async () => navigator.serviceWorker.dispatchEvent(new Event("controllerchange")));
    await waitFor(() => expect(screen.getByLabelText("Technical title")).toBeInTheDocument());
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

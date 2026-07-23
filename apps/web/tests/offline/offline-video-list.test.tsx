// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  reconcile: vi.fn(), listCompleted: vi.fn(), estimate: vi.fn(), deleteVideo: vi.fn(), clearLibrary: vi.fn(),
  sources: new Map<string, { url: string; revoke: ReturnType<typeof vi.fn> }>(),
}));

vi.mock("../../lib/offline/reconciliation", () => ({ reconcileOfflineLibrary: mocks.reconcile }));
vi.mock("../../lib/offline/repository", () => ({ listCompletedOfflineVideos: mocks.listCompleted }));
vi.mock("../../lib/offline/storage", () => ({ getStorageEstimate: mocks.estimate }));
vi.mock("../../lib/offline/library-management", () => ({
  deleteOfflineLibraryVideo: mocks.deleteVideo,
  clearOfflineLibrary: mocks.clearLibrary,
}));
vi.mock("../../lib/offline/playback-source", () => ({
  createOfflinePlaybackSource: vi.fn(async (id: string) => mocks.sources.get(id)!),
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
  mocks.sources.clear();
  for (const record of records) mocks.sources.set(record.id, { url: `blob:${record.id}`, revoke: vi.fn() });
  mocks.reconcile.mockResolvedValue({ errors: [] });
  mocks.listCompleted.mockImplementation(async () => records);
  mocks.estimate.mockResolvedValue({ usage: 100, quota: 1000, available: 900, isAvailable: true });
  mocks.deleteVideo.mockImplementation(async (id: string) => { records = records.filter((record) => record.id !== id); });
  mocks.clearLibrary.mockImplementation(async () => { records = []; });
  vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
  vi.stubGlobal("confirm", vi.fn(() => true));
  vi.spyOn(globalThis, "fetch");
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => undefined);
});

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("OfflineVideoList management", () => {
  it("deletes an item, blocks repeat action, updates summary and revokes its source", async () => {
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
    expect(mocks.sources.get(VIDEO_ID_ONE)?.revoke).toHaveBeenCalled();
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

  it("clears the library, blocks repeat action, revokes active sources and never fetches backend", async () => {
    let finish!: () => void;
    mocks.clearLibrary.mockImplementationOnce(() => new Promise<void>((resolve) => { finish = () => { records = []; resolve(); }; }));
    render(<OfflineVideoList />);
    await screen.findByText("First");
    fireEvent.click(screen.getByRole("button", { name: "Очистить офлайн-библиотеку" }));
    expect(await screen.findByRole("button", { name: "Очистка…" })).toBeDisabled();
    finish();
    expect(await screen.findByText("Офлайн-библиотека пуста")).toBeInTheDocument();
    expect(mocks.sources.get(VIDEO_ID_ONE)?.revoke).toHaveBeenCalled();
    expect(mocks.sources.get(VIDEO_ID_TWO)?.revoke).toHaveBeenCalled();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

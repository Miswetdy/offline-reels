// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VideoList } from "../components/video-list";
import * as videosApi from "../lib/api/videos";
import { VideoCatalogError } from "../lib/api/videos";

const videoOne = {
  id: "video-one",
  title: "First video",
  content_type: "video/mp4",
  byte_size: 12,
  created_at: "2026-07-20T12:00:00Z",
};
const videoTwo = { ...videoOne, id: "video-two", title: "Second video" };
const videoThree = { ...videoOne, id: "video-three", title: "Third video" };
const videoFour = { ...videoOne, id: "video-four", title: "Fourth video" };

type TriggerEntry = { target: Element; ratio: number };

class MockIntersectionObserver {
  static instances: MockIntersectionObserver[] = [];

  readonly observe = vi.fn();
  readonly unobserve = vi.fn();
  readonly disconnect = vi.fn();

  constructor(
    private readonly callback: IntersectionObserverCallback,
    readonly options?: IntersectionObserverInit,
  ) {
    MockIntersectionObserver.instances.push(this);
  }

  trigger(entries: TriggerEntry[]) {
    this.callback(
      entries.map(
        ({ target, ratio }) =>
          ({ target, isIntersecting: ratio > 0, intersectionRatio: ratio }) as IntersectionObserverEntry,
      ),
      this as unknown as IntersectionObserver,
    );
  }
}

function observerFor(target: Element): MockIntersectionObserver {
  const observer = MockIntersectionObserver.instances.find((candidate) =>
    candidate.observe.mock.calls.some(([observed]) => observed === target),
  );
  if (!observer) throw new Error("Observer was not attached to the expected target.");
  return observer;
}

function playerFor(label: string): HTMLVideoElement {
  return screen.getByLabelText(label).querySelector("video") as HTMLVideoElement;
}

function sourcedPlayers(): HTMLVideoElement[] {
  return [...screen.getByLabelText("Video feed").querySelectorAll("video")].filter((video) =>
    video.hasAttribute("src"),
  );
}

function setRect(element: Element, top: number, height = 100) {
  Object.defineProperty(element, "getBoundingClientRect", {
    configurable: true,
    value: () => ({ top, height }),
  });
}

function setOnline(value: boolean) {
  Object.defineProperty(window.navigator, "onLine", { configurable: true, value });
}

beforeEach(() => {
  setOnline(true);
  MockIntersectionObserver.instances = [];
  vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("VideoList", () => {
  it("shows a controlled offline state and retries after the online event", async () => {
    setOnline(false);
    const getVideos = vi.spyOn(videosApi, "getVideos")
      .mockRejectedValueOnce(new VideoCatalogError("network"))
      .mockResolvedValueOnce({ items: [videoOne], next_cursor: null });

    render(<VideoList />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Нет подключения к сети. Онлайн-лента недоступна.");
    expect(screen.getByRole("link", { name: "Открыть офлайн-библиотеку" })).toHaveAttribute("href", "/offline");
    expect(screen.queryByText("First video")).not.toBeInTheDocument();

    setOnline(true);
    fireEvent(window, new Event("online"));
    fireEvent.click(await screen.findByRole("button", { name: "Повторить загрузку" }));

    expect(await screen.findByText("First video")).toBeInTheDocument();
    expect(getVideos).toHaveBeenCalledTimes(2);
  });

  it("keeps an online API failure separate from the offline state", async () => {
    vi.spyOn(videosApi, "getVideos").mockRejectedValueOnce(new VideoCatalogError("http"));

    render(<VideoList />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load videos.");
    expect(screen.queryByRole("link", { name: "Открыть офлайн-библиотеку" })).not.toBeInTheDocument();
  });

  it("shows the offline state when a catalog fetch fails even when navigator.onLine remains true", async () => {
    setOnline(true);
    vi.spyOn(videosApi, "getVideos").mockRejectedValueOnce(new VideoCatalogError("network"));

    render(<VideoList />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Нет подключения к сети. Онлайн-лента недоступна.");
    expect(screen.getByRole("link", { name: "Открыть офлайн-библиотеку" })).toHaveAttribute("href", "/offline");
  });

  it("shows initial loading, error, and empty states", async () => {
    vi.spyOn(videosApi, "getVideos").mockReturnValue(new Promise(() => {}));
    const view = render(<VideoList />);
    expect(screen.getByText("Loading videos…")).toBeInTheDocument();
    view.unmount();

    const getVideos = vi.spyOn(videosApi, "getVideos");
    getVideos.mockRejectedValueOnce(new Error("unavailable"));
    render(<VideoList />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load videos.");

    getVideos.mockResolvedValueOnce({ items: [], next_cursor: null });
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No videos are available yet.")).toBeInTheDocument();
  });

  it("uses a two-player media window without removing feed cards", async () => {
    vi.spyOn(videosApi, "getVideos").mockResolvedValue({
      items: [videoOne, videoTwo, videoThree, videoFour],
      next_cursor: null,
    });
    render(<VideoList />);
    await screen.findByText("First video");

    await waitFor(() => expect(sourcedPlayers()).toHaveLength(2));
    expect(playerFor("First video")).toHaveAttribute(
      "src",
      "http://localhost:8000/videos/video-one/stream",
    );
    expect(playerFor("First video")).toHaveAttribute("preload", "auto");
    expect(playerFor("Second video")).toHaveAttribute("preload", "metadata");
    expect(playerFor("Third video")).not.toHaveAttribute("src");
    expect(playerFor("Third video")).toHaveAttribute("preload", "none");
    expect(screen.getByLabelText("Fourth video")).toBeInTheDocument();
  });

  it("switches the media window, pauses old videos, and releases far media once", async () => {
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    const load = vi.spyOn(HTMLMediaElement.prototype, "load");
    vi.spyOn(videosApi, "getVideos").mockResolvedValue({
      items: [videoOne, videoTwo, videoThree, videoFour],
      next_cursor: null,
    });
    render(<VideoList />);
    const first = await screen.findByLabelText("First video");
    const third = screen.getByLabelText("Third video");
    await waitFor(() => expect(sourcedPlayers()).toHaveLength(2));
    pause.mockClear();
    load.mockClear();

    observerFor(first).trigger([{ target: third, ratio: 0.9 }]);

    await waitFor(() => expect(playerFor("Third video")).toHaveAttribute("src"));
    expect(sourcedPlayers()).toHaveLength(2);
    expect(playerFor("First video")).not.toHaveAttribute("src");
    expect(playerFor("Second video")).not.toHaveAttribute("src");
    expect(playerFor("Third video")).toHaveAttribute("preload", "auto");
    expect(playerFor("Fourth video")).toHaveAttribute("preload", "metadata");
    expect(pause).toHaveBeenCalled();
    expect(load).toHaveBeenCalledTimes(4);

    load.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Turn sound on" }));
    expect(load).not.toHaveBeenCalled();
  });

  it("uses stored ratios and the feed center when a browser reports only partial observer entries", async () => {
    vi.spyOn(videosApi, "getVideos").mockResolvedValue({
      items: [videoOne, videoTwo, videoThree, videoFour],
      next_cursor: null,
    });
    render(<VideoList />);
    const feed = await screen.findByLabelText("Video feed");
    const first = screen.getByLabelText("First video");
    const second = screen.getByLabelText("Second video");
    const third = screen.getByLabelText("Third video");
    const fourth = screen.getByLabelText("Fourth video");
    setRect(feed, 0);
    setRect(first, 0);
    setRect(second, 100);
    setRect(third, 200);
    setRect(fourth, 300);
    observerFor(first).trigger([{ target: first, ratio: 1 }]);
    await waitFor(() => expect(playerFor("First video")).toHaveAttribute("src"));

    setRect(first, -200);
    setRect(second, -100);
    setRect(third, 0);
    setRect(fourth, 100);
    observerFor(first).trigger([{ target: third, ratio: 1 }]);

    await waitFor(() => expect(playerFor("Third video")).toHaveAttribute("src"));
    expect(playerFor("Fourth video")).toHaveAttribute("src");
    expect(playerFor("First video")).not.toHaveAttribute("src");
    expect(playerFor("Second video")).not.toHaveAttribute("src");
    expect(sourcedPlayers()).toHaveLength(2);
  });

  it("breaks equal ratios by feed center, then preserves the current active video", async () => {
    vi.spyOn(videosApi, "getVideos").mockResolvedValue({
      items: [videoOne, videoTwo],
      next_cursor: null,
    });
    render(<VideoList />);
    const feed = await screen.findByLabelText("Video feed");
    const first = screen.getByLabelText("First video");
    const second = screen.getByLabelText("Second video");
    setRect(feed, 0);
    setRect(first, -100);
    setRect(second, 0);
    observerFor(first).trigger([
      { target: first, ratio: 0.5 },
      { target: second, ratio: 0.5 },
    ]);

    await waitFor(() => expect(playerFor("Second video")).toHaveAttribute("preload", "auto"));
    setRect(first, 0);
    setRect(second, 0);
    observerFor(first).trigger([{ target: first, ratio: 0.5 }]);

    expect(playerFor("Second video")).toHaveAttribute("preload", "auto");
  });

  it("uses a requestAnimationFrame scroll fallback when observer state is stale", async () => {
    let runFrame: FrameRequestCallback | undefined;
    const requestAnimationFrame = vi.fn((callback: FrameRequestCallback) => {
      runFrame = callback;
      return 1;
    });
    vi.stubGlobal("requestAnimationFrame", requestAnimationFrame);
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
    vi.spyOn(videosApi, "getVideos").mockResolvedValue({
      items: [videoOne, videoTwo, videoThree, videoFour],
      next_cursor: null,
    });
    render(<VideoList />);
    const feed = await screen.findByLabelText("Video feed");
    setRect(feed, 0);
    setRect(screen.getByLabelText("First video"), -200);
    setRect(screen.getByLabelText("Second video"), -100);
    setRect(screen.getByLabelText("Third video"), 0);
    setRect(screen.getByLabelText("Fourth video"), 100);
    await waitFor(() => expect(playerFor("First video")).toHaveAttribute("src"));

    fireEvent.scroll(feed);
    fireEvent.scroll(feed);
    expect(requestAnimationFrame).toHaveBeenCalledTimes(1);
    runFrame?.(0);

    await waitFor(() => expect(playerFor("Third video")).toHaveAttribute("src"));
    expect(playerFor("Fourth video")).toHaveAttribute("src");
    expect(sourcedPlayers()).toHaveLength(2);
  });

  it("starts only the active video after it is ready and handles rejection locally", async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockRejectedValue(new Error("blocked"));
    vi.spyOn(videosApi, "getVideos").mockResolvedValue({ items: [videoOne, videoTwo], next_cursor: null });
    render(<VideoList />);
    await screen.findByText("First video");
    const first = playerFor("First video");
    await waitFor(() => expect(first).toHaveAttribute("src"));
    expect(first).toHaveProperty("muted", true);

    fireEvent.canPlay(first);
    await waitFor(() => expect(play).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("This video could not be played.")).toBeInTheDocument();
    expect(screen.getByText("Second video")).toBeInTheDocument();
  });

  it("cancels stale playback after a rapid active-video switch", async () => {
    let resolveFirstPlay: (() => void) | undefined;
    const firstPlay = new Promise<void>((resolve) => {
      resolveFirstPlay = resolve;
    });
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    vi.spyOn(HTMLMediaElement.prototype, "play")
      .mockReturnValueOnce(firstPlay)
      .mockResolvedValue(undefined);
    vi.spyOn(videosApi, "getVideos").mockResolvedValue({ items: [videoOne, videoTwo], next_cursor: null });
    render(<VideoList />);
    const firstSection = await screen.findByLabelText("First video");
    const secondSection = screen.getByLabelText("Second video");
    const first = playerFor("First video");
    const second = playerFor("Second video");

    fireEvent.canPlay(first);
    observerFor(firstSection).trigger([{ target: secondSection, ratio: 0.9 }]);
    fireEvent.canPlay(second);
    resolveFirstPlay?.();

    await waitFor(() => expect(pause).toHaveBeenCalled());
  });

  it("applies shared sound state to every mounted video", async () => {
    vi.spyOn(videosApi, "getVideos").mockResolvedValue({ items: [videoOne, videoTwo], next_cursor: null });
    render(<VideoList />);
    await screen.findByText("First video");

    fireEvent.click(screen.getByRole("button", { name: "Turn sound on" }));
    expect(playerFor("First video")).toHaveProperty("muted", false);
    expect(playerFor("Second video")).toHaveProperty("muted", false);
    expect(screen.getByRole("button", { name: "Mute videos" })).toHaveAttribute("aria-pressed", "true");
  });

  it("keeps a per-video playback error local to that card", async () => {
    vi.spyOn(videosApi, "getVideos").mockResolvedValue({ items: [videoOne, videoTwo], next_cursor: null });
    render(<VideoList />);
    await screen.findByText("First video");
    fireEvent.error(playerFor("First video"));

    expect(await screen.findByText("This video could not be played.")).toBeInTheDocument();
    expect(screen.getByText("Second video")).toBeInTheDocument();
  });

  it("uses a non-zero sentinel inside the feed root and loads one next page", async () => {
    const getVideos = vi.spyOn(videosApi, "getVideos");
    getVideos
      .mockResolvedValueOnce({ items: [videoOne], next_cursor: "cursor-one" })
      .mockResolvedValueOnce({ items: [videoOne, videoTwo], next_cursor: null });
    render(<VideoList />);
    await screen.findByText("First video");
    const feed = screen.getByLabelText("Video feed");
    const sentinel = screen.getByTestId("feed-sentinel");
    await waitFor(() => expect(() => observerFor(sentinel)).not.toThrow());
    const sentinelObserver = observerFor(sentinel);

    expect(sentinel).toHaveClass("h-px", "shrink-0");
    expect(sentinelObserver.options?.root).toBe(feed);
    sentinelObserver.trigger([{ target: sentinel, ratio: 1 }]);
    sentinelObserver.trigger([{ target: sentinel, ratio: 1 }]);

    expect(await screen.findByText("Second video")).toBeInTheDocument();
    expect(getVideos).toHaveBeenCalledTimes(2);
    expect(getVideos.mock.calls[1][0]).toMatchObject({ limit: 5, cursor: "cursor-one" });
    expect(screen.getByText("You reached the end of the feed.")).toBeInTheDocument();
  });

  it("keeps current videos after a next-page error and retries the same cursor", async () => {
    const getVideos = vi.spyOn(videosApi, "getVideos");
    getVideos
      .mockResolvedValueOnce({ items: [videoOne], next_cursor: "retry-cursor" })
      .mockRejectedValueOnce(new Error("temporary failure"))
      .mockResolvedValueOnce({ items: [videoTwo], next_cursor: null });
    render(<VideoList />);
    await screen.findByText("First video");
    const sentinel = screen.getByTestId("feed-sentinel");
    await waitFor(() => expect(() => observerFor(sentinel)).not.toThrow());
    observerFor(sentinel).trigger([{ target: sentinel, ratio: 1 }]);

    expect(await screen.findByText("Unable to load more videos.")).toBeInTheDocument();
    expect(screen.getByText("First video")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry loading more" }));
    expect(await screen.findByText("Second video")).toBeInTheDocument();
    expect(getVideos.mock.calls[2][0]).toMatchObject({ limit: 5, cursor: "retry-cursor" });
  });

  it("does not create a next-page observer after next_cursor is null", async () => {
    const getVideos = vi.spyOn(videosApi, "getVideos").mockResolvedValue({ items: [videoThree], next_cursor: null });
    render(<VideoList />);
    await screen.findByText("Third video");

    expect(screen.getByText("You reached the end of the feed.")).toBeInTheDocument();
    expect(() => observerFor(screen.getByTestId("feed-sentinel"))).toThrow();
    expect(getVideos).toHaveBeenCalledTimes(1);
  });
});

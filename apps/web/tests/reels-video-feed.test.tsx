// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  REELS_EDGE_ZONE_FRACTION,
  REELS_HOLD_DELAY_MS,
  REELS_MOVEMENT_SLOP_PX,
  VerticalVideoFeed,
  type VerticalVideoFeedItem,
} from "../components/vertical-video-feed";
import { AppBottomNavigation } from "../components/app-bottom-navigation";

const items: VerticalVideoFeedItem[] = [
  { id: "one", title: "First video", mediaUrl: "https://media.test/one.mp4" },
  { id: "two", title: "Second video", mediaUrl: "https://media.test/two.mp4" },
  { id: "three", title: "Third video", mediaUrl: "https://media.test/three.mp4" },
  { id: "four", title: "Fourth video", mediaUrl: "https://media.test/four.mp4" },
];

type TriggerEntry = { target: Element; ratio: number };

class MockIntersectionObserver {
  static instances: MockIntersectionObserver[] = [];

  readonly observe = vi.fn();
  readonly disconnect = vi.fn();

  constructor(private readonly callback: IntersectionObserverCallback) {
    MockIntersectionObserver.instances.push(this);
  }

  trigger(entries: TriggerEntry[]) {
    this.callback(
      entries.map(({ target, ratio }) => ({
        target,
        isIntersecting: ratio > 0,
        intersectionRatio: ratio,
      }) as IntersectionObserverEntry),
      this as unknown as IntersectionObserver,
    );
  }
}

const pausedState = new WeakMap<HTMLMediaElement, boolean>();

function playerFor(label: string): HTMLVideoElement {
  return screen.getByLabelText(label).querySelector("video") as HTMLVideoElement;
}

function observerFor(target: Element): MockIntersectionObserver {
  const observer = MockIntersectionObserver.instances.find((candidate) =>
    candidate.observe.mock.calls.some(([observed]) => observed === target),
  );
  if (!observer) throw new Error("Observer was not attached to the expected target.");
  return observer;
}

function gestureFor(itemId = "one"): HTMLElement {
  const gesture = screen.getByTestId(`reels-gesture-${itemId}`);
  Object.defineProperty(gesture, "getBoundingClientRect", {
    configurable: true,
    value: () => ({ left: 0, top: 0, width: 100, height: 200 }),
  });
  return gesture;
}

function pointerDown(target: Element, clientX: number, pointerId = 1) {
  fireEvent.pointerDown(target, { button: 0, clientX, clientY: 100, isPrimary: true, pointerId });
}

function pointerMove(target: Element, clientX: number, clientY: number, pointerId = 1) {
  fireEvent.pointerMove(target, { clientX, clientY, isPrimary: true, pointerId });
}

function pointerUp(target: Element, clientX: number, pointerId = 1) {
  fireEvent.pointerUp(target, { button: 0, clientX, clientY: 100, isPrimary: true, pointerId });
}

function advanceHold() {
  act(() => vi.advanceTimersByTime(REELS_HOLD_DELAY_MS));
}

beforeEach(() => {
  vi.useFakeTimers();
  MockIntersectionObserver.instances = [];
  vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
  vi.spyOn(HTMLMediaElement.prototype, "paused", "get").mockImplementation(function paused(this: HTMLMediaElement) {
    return pausedState.get(this) ?? true;
  });
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function play(this: HTMLMediaElement) {
    pausedState.set(this, false);
    return Promise.resolve();
  });
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(function pause(this: HTMLMediaElement) {
    pausedState.set(this, true);
  });
  vi.spyOn(fireEvent, "canPlay").mockImplementation(fireEvent.loadedMetadata);
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("VerticalVideoFeed Reels-like controls", () => {
  it("uses 10 percent edge zones and keeps the remaining area central", () => {
    expect(REELS_EDGE_ZONE_FRACTION).toBe(0.1);
  });

  it("removes native controls, enables loop, and preserves the three-source preload window", () => {
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);

    const first = playerFor("First video");
    expect(first).not.toHaveAttribute("controls");
    expect(first).toHaveAttribute("loop");
    expect(first).toHaveAttribute("playsinline");
    expect(first).toHaveClass("object-cover");
    expect(first).toHaveAttribute("draggable", "false");
    expect(first).toHaveAttribute("preload", "auto");
    expect(playerFor("Second video")).toHaveAttribute("preload", "metadata");
    expect(playerFor("Third video")).not.toHaveAttribute("src");
    expect(document.querySelectorAll("video[src]")).toHaveLength(2);
    fireEvent.canPlay(first);
    expect(first).toHaveProperty("paused", false);

    const firstSection = screen.getByLabelText("First video");
    const secondSection = screen.getByLabelText("Second video");
    act(() => observerFor(firstSection).trigger([{ target: secondSection, ratio: 1 }]));
    fireEvent.canPlay(playerFor("Second video"));

    expect(playerFor("First video")).toHaveAttribute("preload", "metadata");
    expect(playerFor("Second video")).toHaveAttribute("preload", "auto");
    expect(playerFor("Third video")).toHaveAttribute("preload", "metadata");
    expect(document.querySelectorAll("video[src]")).toHaveLength(3);
    expect(first).toHaveProperty("paused", true);
    expect(playerFor("Second video")).toHaveProperty("paused", false);
    expect(playerFor("Third video")).toHaveProperty("paused", true);
  });

  it("starts Reels with sound enabled and attempts audible startup playback", () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const first = playerFor("First video");

    expect(first.muted).toBe(false);
    fireEvent.loadedMetadata(first);

    expect(play.mock.contexts).toContain(first);
    expect(first.muted).toBe(false);
  });

  it("keeps sound enabled and exposes Play when audible startup is blocked, then resumes from a user tap", async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play")
      .mockRejectedValueOnce(new DOMException("blocked", "NotAllowedError"));
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const first = playerFor("First video");
    fireEvent.loadedMetadata(first);
    await act(async () => Promise.resolve());

    expect(first.muted).toBe(false);
    expect(screen.getByTestId("reels-controls-one")).toHaveClass("opacity-100");
    expect(screen.getByRole("button", { name: "Воспроизвести видео" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    const gesture = gestureFor();
    pointerDown(gesture, 50);
    pointerUp(gesture, 50);
    expect(play).toHaveBeenCalledTimes(2);
    expect(first.muted).toBe(false);
    expect(screen.getByTestId("reels-controls-one")).toHaveClass("opacity-100");

    fireEvent.play(first);
    expect(screen.getByTestId("reels-controls-one")).toHaveClass("opacity-0");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("does not render inactive Reels metadata while a partially visible card loses active status", () => {
    render(<VerticalVideoFeed items={items} controlsMode="reels" showMetadata={false} />);
    const firstSection = screen.getByLabelText("First video");
    const secondSection = screen.getByLabelText("Second video");

    act(() => observerFor(firstSection).trigger([
      { target: firstSection, ratio: 0.4 },
      { target: secondSection, ratio: 0.6 },
    ]));

    expect(screen.queryByTestId("reels-bottom-layout-one")).not.toBeInTheDocument();
    expect(screen.queryByTestId("reels-metadata-one")).not.toBeInTheDocument();
    expect(screen.queryByText("First video")).not.toBeInTheDocument();
    expect(screen.getByTestId("reels-progress-two")).toBeInTheDocument();

    act(() => observerFor(firstSection).trigger([
      { target: firstSection, ratio: 0.6 },
      { target: secondSection, ratio: 0.4 },
    ]));
    expect(screen.getByTestId("reels-progress-one")).toBeInTheDocument();
    expect(screen.queryByTestId("reels-bottom-layout-two")).not.toBeInTheDocument();
  });

  it("shows a Russian terminal error only for an actual active media error", async () => {
    render(<VerticalVideoFeed items={items} controlsMode="reels" showMetadata={false} />);
    const first = playerFor("First video");

    fireEvent.error(first);

    expect(screen.getByRole("alert")).toHaveTextContent("Не удалось воспроизвести видео.");
    expect(first).not.toHaveAttribute("src");
  });

  it("ignores a stale inactive media error instead of rendering an error or metadata overlay", () => {
    render(<VerticalVideoFeed items={items} controlsMode="reels" showMetadata={false} />);
    const firstSection = screen.getByLabelText("First video");
    const secondSection = screen.getByLabelText("Second video");
    const first = playerFor("First video");

    act(() => observerFor(firstSection).trigger([
      { target: firstSection, ratio: 0.4 },
      { target: secondSection, ratio: 0.6 },
    ]));
    fireEvent.error(first);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByTestId("reels-bottom-layout-one")).not.toBeInTheDocument();
    expect(playerFor("Second video")).toHaveAttribute("src", items[1].mediaUrl);
  });

  it("ignores a stale audible-start rejection after the active item changes", async () => {
    let rejectFirstStart: ((reason?: unknown) => void) | undefined;
    const firstStart = new Promise<void>((_resolve, reject) => {
      rejectFirstStart = reject;
    });
    let first: HTMLVideoElement;
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function play(this: HTMLMediaElement) {
      return this === first ? firstStart : Promise.resolve();
    });
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const firstSection = screen.getByLabelText("First video");
    const secondSection = screen.getByLabelText("Second video");
    first = playerFor("First video");
    fireEvent.loadedMetadata(first);
    act(() => observerFor(firstSection).trigger([
      { target: firstSection, ratio: 0 },
      { target: secondSection, ratio: 1 },
    ]));
    const second = playerFor("Second video");
    fireEvent.loadedMetadata(second);

    rejectFirstStart?.(new DOMException("blocked", "NotAllowedError"));
    await act(async () => Promise.resolve());

    expect(screen.getByTestId("reels-controls-two")).toHaveClass("opacity-0");
    expect(second.muted).toBe(false);
  });

  it("uses a short center tap to pause, then hides controls only after the current video plays", () => {
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const video = playerFor("First video");
    fireEvent.canPlay(video);
    pause.mockClear();
    const gesture = gestureFor();

    pointerDown(gesture, 50);
    pointerUp(gesture, 50);

    expect(pause.mock.contexts).toContain(video);
    expect(screen.getByTestId("reels-controls-one")).toHaveClass("opacity-100");
    expect(screen.getByRole("button", { name: "Воспроизвести видео" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "Выключить звук" })).toHaveAttribute("aria-pressed", "true");

    fireEvent.play(video);
    expect(screen.getByTestId("reels-controls-one")).toHaveClass("opacity-100");

    pointerDown(gesture, 50, 2);
    pointerUp(gesture, 50, 2);
    expect(video).toHaveProperty("paused", false);
    expect(screen.getByTestId("reels-controls-one")).toHaveClass("opacity-100");

    fireEvent.play(video);
    expect(screen.getByTestId("reels-controls-one")).toHaveClass("opacity-0");
  });

  it("hides tap controls after the central play button receives the current play event", () => {
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const video = playerFor("First video");
    fireEvent.canPlay(video);
    const gesture = gestureFor();
    pointerDown(gesture, 50);
    pointerUp(gesture, 50);

    fireEvent.click(screen.getByRole("button", { name: "Воспроизвести видео" }));
    expect(screen.getByTestId("reels-controls-one")).toHaveClass("opacity-100");
    fireEvent.play(video);
    expect(screen.getByTestId("reels-controls-one")).toHaveClass("opacity-0");
  });

  it("keeps tap controls available when an explicit resume play() is rejected", async () => {
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const video = playerFor("First video");
    fireEvent.canPlay(video);
    const gesture = gestureFor();
    pointerDown(gesture, 50);
    pointerUp(gesture, 50);
    vi.spyOn(HTMLMediaElement.prototype, "play").mockRejectedValueOnce(new DOMException("blocked", "NotAllowedError"));

    pointerDown(gesture, 50, 2);
    pointerUp(gesture, 50, 2);
    await act(async () => Promise.resolve());

    expect(screen.getByTestId("reels-controls-one")).toHaveClass("opacity-100");
    expect(screen.getByRole("button", { name: "Воспроизвести видео" })).toBeInTheDocument();
  });

  it("keeps controls visible when a stale same-item play event follows a newer tap pause", () => {
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const video = playerFor("First video");
    fireEvent.canPlay(video);
    const gesture = gestureFor();

    pointerDown(gesture, 50);
    pointerUp(gesture, 50);
    expect(screen.getByTestId("reels-controls-one")).toHaveClass("opacity-100");

    pointerDown(gesture, 50, 2);
    pointerUp(gesture, 50, 2);
    expect(video).toHaveProperty("paused", false);

    pointerDown(gesture, 50, 3);
    pointerUp(gesture, 50, 3);
    expect(video).toHaveProperty("paused", true);

    fireEvent.play(video);

    expect(screen.getByTestId("reels-controls-one")).toHaveClass("opacity-100");
    expect(screen.getByRole("button", { name: "Воспроизвести видео" })).toBeInTheDocument();
  });

  it("does not let a stale play event hide controls for a newly active item", () => {
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const firstSection = screen.getByLabelText("First video");
    const secondSection = screen.getByLabelText("Second video");
    const first = playerFor("First video");
    fireEvent.canPlay(first);
    act(() => observerFor(firstSection).trigger([
      { target: firstSection, ratio: 0 },
      { target: secondSection, ratio: 1 },
    ]));
    const second = playerFor("Second video");
    fireEvent.canPlay(second);
    const secondGesture = gestureFor("two");
    pointerDown(secondGesture, 50, 2);
    pointerUp(secondGesture, 50, 2);
    expect(screen.getByTestId("reels-controls-two")).toHaveClass("opacity-100");

    fireEvent.play(first);

    expect(screen.getByTestId("reels-controls-two")).toHaveClass("opacity-100");
  });

  it("lets the mute button change only the shared muted state", () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const video = playerFor("First video");
    fireEvent.canPlay(video);
    const gesture = gestureFor();
    pointerDown(gesture, 50);
    pointerUp(gesture, 50);
    play.mockClear();
    pause.mockClear();

    fireEvent.pointerDown(screen.getByRole("button", { name: "Выключить звук" }), {
      button: 0,
      isPrimary: true,
      pointerId: 2,
    });
    fireEvent.click(screen.getByRole("button", { name: "Выключить звук" }));

    expect(video.muted).toBe(true);
    expect(play).not.toHaveBeenCalled();
    expect(pause).not.toHaveBeenCalled();
    advanceHold();
    expect(screen.queryByText("2×")).not.toBeInTheDocument();
  });

  it("temporarily pauses a playing center hold and resumes only that active video on release", async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const video = playerFor("First video");
    fireEvent.canPlay(video);
    play.mockClear();
    pause.mockClear();
    const gesture = gestureFor();

    pointerDown(gesture, 50);
    advanceHold();
    expect(pause.mock.contexts).toEqual([video]);
    expect(play).not.toHaveBeenCalled();
    expect(screen.getByTestId("reels-controls-one")).toHaveClass("opacity-0");

    pointerUp(gesture, 50);
    expect(play.mock.contexts).toEqual([video]);
    expect(screen.getByTestId("reels-controls-one")).toHaveClass("opacity-0");
    await act(async () => Promise.resolve());
    expect(playerFor("Second video")).toHaveProperty("paused", true);
  });

  it("does not start a video that was paused before a center hold", () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    play.mockClear();
    pause.mockClear();
    const gesture = gestureFor();

    pointerDown(gesture, 50);
    advanceHold();
    pointerUp(gesture, 50);

    expect(play).not.toHaveBeenCalled();
    expect(pause).not.toHaveBeenCalled();
    expect(screen.getByTestId("reels-controls-one")).toHaveClass("opacity-0");
  });

  it.each([
    ["left boundary", 10, "left-edge"],
    ["right boundary", 90, "right-edge"],
    ["right outer edge", 100, "right-edge"],
  ])("uses a %s edge hold for temporary 2x without changing playback", (_name, clientX, zone) => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const video = playerFor("First video");
    video.playbackRate = 1.25;
    play.mockClear();
    pause.mockClear();
    const gesture = gestureFor();

    pointerDown(gesture, clientX);
    advanceHold();
    expect(video.playbackRate).toBe(2);
    expect(screen.getByTestId(`reels-speed-${zone}`)).toHaveTextContent("2×");
    expect(screen.getByTestId("reels-controls-one")).toHaveClass("opacity-0");
    expect(play).not.toHaveBeenCalled();
    expect(pause).not.toHaveBeenCalled();

    pointerUp(gesture, clientX);
    expect(video.playbackRate).toBe(1.25);
    expect(screen.queryByTestId(`reels-speed-${zone}`)).not.toBeInTheDocument();
    expect(play).not.toHaveBeenCalled();
  });

  it("changes only playbackRate across an edge hold and keeps the same playing video instance", () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    const load = vi.spyOn(HTMLMediaElement.prototype, "load");
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const video = playerFor("First video");
    fireEvent.canPlay(video);
    const initialVideo = playerFor("First video");
    const initialSrc = video.getAttribute("src");
    let currentTime = 7;
    const setCurrentTime = vi.fn((value: number) => {
      currentTime = value;
    });
    Object.defineProperty(video, "currentTime", {
      configurable: true,
      get: () => currentTime,
      set: setCurrentTime,
    });
    play.mockClear();
    pause.mockClear();
    load.mockClear();
    const gesture = gestureFor();

    pointerDown(gesture, 10);
    expect(video).toBe(initialVideo);
    expect(video).toHaveProperty("paused", false);
    expect(video.playbackRate).toBe(1);
    expect(play).not.toHaveBeenCalled();
    expect(pause).not.toHaveBeenCalled();

    advanceHold();
    expect(video).toBe(playerFor("First video"));
    expect(video).toHaveProperty("paused", false);
    expect(video.playbackRate).toBe(2);
    expect(screen.getByTestId("reels-speed-left-edge")).toBeInTheDocument();
    expect(video.getAttribute("src")).toBe(initialSrc);
    expect(video.currentTime).toBe(7);
    expect(setCurrentTime).not.toHaveBeenCalled();
    expect(play).not.toHaveBeenCalled();
    expect(pause).not.toHaveBeenCalled();
    expect(load).not.toHaveBeenCalled();

    pointerUp(gesture, 10);
    expect(video).toBe(playerFor("First video"));
    expect(video).toHaveProperty("paused", false);
    expect(video.playbackRate).toBe(1);
    expect(screen.queryByTestId("reels-speed-left-edge")).not.toBeInTheDocument();
    expect(video.getAttribute("src")).toBe(initialSrc);
    expect(video.currentTime).toBe(7);
    expect(setCurrentTime).not.toHaveBeenCalled();
    expect(play).not.toHaveBeenCalled();
    expect(pause).not.toHaveBeenCalled();
    expect(load).not.toHaveBeenCalled();
  });

  it("does not set preservesPitch during production edge holds", () => {
    const original = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, "preservesPitch");
    const setPreservesPitch = vi.fn();
    Object.defineProperty(HTMLMediaElement.prototype, "preservesPitch", {
      configurable: true,
      get: () => true,
      set: setPreservesPitch,
    });
    try {
      render(<VerticalVideoFeed items={items} controlsMode="reels" />);
      const video = playerFor("First video");
      fireEvent.canPlay(video);

      const gesture = gestureFor();
      pointerDown(gesture, 10);
      advanceHold();
      pointerUp(gesture, 10);

      expect(video.playbackRate).toBe(1);
      expect(setPreservesPitch).not.toHaveBeenCalled();
    } finally {
      if (original) Object.defineProperty(HTMLMediaElement.prototype, "preservesPitch", original);
      else Reflect.deleteProperty(HTMLMediaElement.prototype, "preservesPitch");
    }
  });

  it("does not start a paused video during an edge hold", () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const video = playerFor("First video");
    const gesture = gestureFor();
    play.mockClear();
    pause.mockClear();

    pointerDown(gesture, 10);
    advanceHold();
    expect(video).toHaveProperty("paused", true);
    expect(video.playbackRate).toBe(2);
    pointerUp(gesture, 10);

    expect(video).toHaveProperty("paused", true);
    expect(video.playbackRate).toBe(1);
    expect(play).not.toHaveBeenCalled();
    expect(pause).not.toHaveBeenCalled();
  });

  it("restores edge speed on cancellation without resuming the held video", () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const video = playerFor("First video");
    fireEvent.canPlay(video);
    const gesture = gestureFor();
    const feed = screen.getByLabelText("Video feed");
    play.mockClear();
    pause.mockClear();

    pointerDown(gesture, 10, 1);
    advanceHold();
    fireEvent.pointerCancel(gesture, { pointerId: 1 });
    expect(video.playbackRate).toBe(1);

    pointerDown(gesture, 90, 2);
    advanceHold();
    pointerMove(gesture, 90, 100 + REELS_MOVEMENT_SLOP_PX + 1, 2);
    expect(video.playbackRate).toBe(1);

    pointerDown(gesture, 10, 3);
    advanceHold();
    fireEvent.scroll(feed);
    expect(video.playbackRate).toBe(1);
    expect(play).not.toHaveBeenCalled();
    expect(pause).not.toHaveBeenCalled();

    pointerDown(gesture, 90, 4);
    advanceHold();
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    expect(video.playbackRate).toBe(1);
    expect(play).not.toHaveBeenCalled();

    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
  });

  it.each([
    ["immediately after the left 10 percent boundary", 11],
    ["immediately before the right 10 percent boundary", 89],
  ])("keeps %s in the center hold zone", (_name, clientX) => {
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const video = playerFor("First video");
    fireEvent.canPlay(video);
    pause.mockClear();
    const gesture = gestureFor();

    pointerDown(gesture, clientX);
    advanceHold();

    expect(video.playbackRate).toBe(1);
    expect(screen.queryByTestId("reels-speed-left-edge")).not.toBeInTheDocument();
    expect(screen.queryByTestId("reels-speed-right-edge")).not.toBeInTheDocument();
    expect(pause.mock.contexts).toContain(video);
  });

  it("keeps pending movement as an ordinary scroll and lets the next item activate", () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const firstSection = screen.getByLabelText("First video");
    const secondSection = screen.getByLabelText("Second video");
    const video = playerFor("First video");
    fireEvent.canPlay(video);
    play.mockClear();
    pause.mockClear();
    const gesture = gestureFor();

    pointerDown(gesture, 50);
    pointerMove(gesture, 50, 100 + REELS_MOVEMENT_SLOP_PX + 1);
    advanceHold();

    expect(play).not.toHaveBeenCalled();
    expect(pause).not.toHaveBeenCalled();
    expect(video.playbackRate).toBe(1);
    act(() => observerFor(firstSection).trigger([
      { target: firstSection, ratio: 0.4 },
      { target: secondSection, ratio: 0.6 },
    ]));
    const second = playerFor("Second video");
    fireEvent.canPlay(second);
    expect(play.mock.contexts).toContain(second);
    expect(screen.queryByText("2×")).not.toBeInTheDocument();
  });

  it("keeps an activated center hold paused through movement until pointer release", () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const video = playerFor("First video");
    fireEvent.canPlay(video);
    play.mockClear();
    pause.mockClear();
    const gesture = gestureFor();

    pointerDown(gesture, 50);
    advanceHold();
    pointerMove(gesture, 50, 100 + REELS_MOVEMENT_SLOP_PX + 1);
    expect(pause.mock.contexts).toContain(video);
    expect(play).not.toHaveBeenCalled();
    expect(video).toHaveProperty("paused", true);
    pointerUp(gesture, 50);
    expect(play.mock.contexts).toContain(video);

    play.mockClear();
    pause.mockClear();
    pointerDown(gesture, 10, 2);
    advanceHold();
    expect(video.playbackRate).toBe(2);
    pointerMove(gesture, 10, 100 + REELS_MOVEMENT_SLOP_PX + 1, 2);
    expect(video.playbackRate).toBe(1);
    expect(play).not.toHaveBeenCalled();
    expect(pause).not.toHaveBeenCalled();
  });

  it("cleans edge holds and keeps center hold paused across pointercancel until the touch ends", () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const video = playerFor("First video");
    const gesture = gestureFor();
    const feed = screen.getByLabelText("Video feed");

    pointerDown(gesture, 10);
    advanceHold();
    fireEvent.pointerCancel(gesture, { pointerId: 1 });
    expect(video.playbackRate).toBe(1);

    pointerDown(gesture, 90, 2);
    advanceHold();
    fireEvent.lostPointerCapture(gesture, { pointerId: 2 });
    expect(video.playbackRate).toBe(1);

    pointerDown(gesture, 10, 3);
    advanceHold();
    fireEvent.scroll(feed);
    expect(video.playbackRate).toBe(1);

    fireEvent.canPlay(video);
    play.mockClear();
    pointerDown(gesture, 50, 6);
    advanceHold();
    fireEvent.pointerCancel(gesture, { pointerId: 6 });
    expect(play).not.toHaveBeenCalled();
    expect(video).toHaveProperty("paused", true);
    fireEvent.touchEnd(document, { touches: [] });
    expect(play.mock.contexts).toContain(video);

    fireEvent.canPlay(video);
    play.mockClear();
    pointerDown(gesture, 50, 7);
    advanceHold();
    fireEvent.pointerCancel(gesture, { pointerId: 7 });
    fireEvent.touchCancel(document, { touches: [] });
    expect(play).not.toHaveBeenCalled();

    pointerDown(gesture, 90, 4);
    advanceHold();
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    expect(video.playbackRate).toBe(1);

    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
    pointerDown(gesture, 10, 5);
    advanceHold();
    act(() => window.dispatchEvent(new Event("pagehide")));
    expect(video.playbackRate).toBe(1);
    expect(screen.queryByText("2×")).not.toBeInTheDocument();
    expect(screen.getByTestId("reels-controls-one")).toHaveClass("opacity-0");
  });

  it("keeps a center-hold lock scoped to A while B activates and only resumes A after a reversal plus release", () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const firstSection = screen.getByLabelText("First video");
    const secondSection = screen.getByLabelText("Second video");
    const first = playerFor("First video");
    fireEvent.canPlay(first);
    play.mockClear();
    pause.mockClear();

    pointerDown(gestureFor("one"), 50);
    advanceHold();
    fireEvent.scroll(screen.getByLabelText("Video feed"));
    expect(play).not.toHaveBeenCalled();
    expect(first).toHaveProperty("paused", true);

    act(() => observerFor(firstSection).trigger([
      { target: firstSection, ratio: 0.4 },
      { target: secondSection, ratio: 0.6 },
    ]));
    const second = playerFor("Second video");
    fireEvent.canPlay(second);
    expect(play.mock.contexts).toContain(second);
    expect(play.mock.contexts).not.toContain(first);
    expect(first).toHaveProperty("paused", true);

    play.mockClear();
    pause.mockClear();
    act(() => observerFor(firstSection).trigger([
      { target: firstSection, ratio: 0.6 },
      { target: secondSection, ratio: 0.4 },
    ]));
    expect(pause.mock.contexts).toContain(second);
    expect(first).toHaveProperty("paused", true);
    expect(play).not.toHaveBeenCalled();

    pointerUp(gestureFor("one"), 50);
    expect(play.mock.contexts).toContain(first);
  });

  it("does not resume a center-held A when the same touch ends while B is active", () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const firstSection = screen.getByLabelText("First video");
    const secondSection = screen.getByLabelText("Second video");
    const first = playerFor("First video");
    fireEvent.canPlay(first);
    play.mockClear();

    pointerDown(gestureFor("one"), 50);
    advanceHold();
    pointerMove(gestureFor("one"), 50, 100 + REELS_MOVEMENT_SLOP_PX + 1);
    act(() => observerFor(firstSection).trigger([
      { target: firstSection, ratio: 0.4 },
      { target: secondSection, ratio: 0.6 },
    ]));
    const second = playerFor("Second video");
    fireEvent.canPlay(second);
    play.mockClear();

    pointerUp(gestureFor("two"), 50);

    expect(play).not.toHaveBeenCalled();
    expect(first).toHaveProperty("paused", true);
    expect(second).toHaveProperty("paused", false);
  });

  it("does not let a stale A play promise revive the held item after B becomes active", async () => {
    let resolveFirstStart!: () => void;
    const firstStart = new Promise<void>((resolve) => {
      resolveFirstStart = resolve;
    });
    let first!: HTMLVideoElement;
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function play(this: HTMLMediaElement) {
      pausedState.set(this, false);
      return this === first ? firstStart : Promise.resolve();
    });
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const firstSection = screen.getByLabelText("First video");
    const secondSection = screen.getByLabelText("Second video");
    first = playerFor("First video");
    fireEvent.canPlay(first);

    pointerDown(gestureFor("one"), 50);
    advanceHold();
    pointerMove(gestureFor("one"), 50, 100 + REELS_MOVEMENT_SLOP_PX + 1);
    act(() => observerFor(firstSection).trigger([
      { target: firstSection, ratio: 0.4 },
      { target: secondSection, ratio: 0.6 },
    ]));
    const second = playerFor("Second video");
    fireEvent.canPlay(second);

    resolveFirstStart();
    await act(async () => Promise.resolve());

    expect(first).toHaveProperty("paused", true);
    expect(second).toHaveProperty("paused", false);
  });

  it("never resumes a center hold that was already paused before the hold", () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const first = playerFor("First video");
    play.mockClear();

    pointerDown(gestureFor("one"), 50);
    advanceHold();
    pointerUp(gestureFor("one"), 50);

    expect(first).toHaveProperty("paused", true);
    expect(play).not.toHaveBeenCalled();
  });

  it("uses inline SVG controls instead of system emoji and keeps scoped interaction suppression in Reels mode", () => {
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const section = screen.getByLabelText("First video");
    const video = playerFor("First video");
    fireEvent.canPlay(video);
    const gesture = gestureFor();
    pointerDown(gesture, 50);
    pointerUp(gesture, 50);
    const playButton = screen.getByRole("button", { name: "Воспроизвести видео" });
    const soundButton = screen.getByRole("button", { name: "Выключить звук" });

    expect(playButton.querySelector("svg[aria-hidden='true']")).toBeInTheDocument();
    expect(soundButton.querySelector("svg[aria-hidden='true']")).toBeInTheDocument();
    expect(playButton).not.toHaveTextContent("▶");
    expect(soundButton).not.toHaveTextContent("🔇");
    expect(section).toHaveClass("reels-interaction-card");
    expect(gesture).toHaveClass("reels-gesture-surface");

    const contextMenu = new MouseEvent("contextmenu", { bubbles: true, cancelable: true });
    section.dispatchEvent(contextMenu);
    expect(contextMenu.defaultPrevented).toBe(true);
  });

  it("invalidates an old hold timer across a rapid 1-to-2-to-1 transition", () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const firstSection = screen.getByLabelText("First video");
    const secondSection = screen.getByLabelText("Second video");
    const firstVideo = playerFor("First video");
    fireEvent.canPlay(firstVideo);
    play.mockClear();
    pause.mockClear();
    const gesture = gestureFor();

    pointerDown(gesture, 10);
    act(() => observerFor(firstSection).trigger([
      { target: firstSection, ratio: 0 },
      { target: secondSection, ratio: 1 },
    ]));
    act(() => observerFor(firstSection).trigger([
      { target: firstSection, ratio: 1 },
      { target: secondSection, ratio: 0 },
    ]));
    const playCallsBeforeTimer = play.mock.calls.length;
    const pauseCallsBeforeTimer = pause.mock.calls.length;
    advanceHold();

    expect(firstVideo.playbackRate).toBe(1);
    expect(screen.queryByText("2×")).not.toBeInTheDocument();
    expect(play).toHaveBeenCalledTimes(playCallsBeforeTimer);
    expect(pause).toHaveBeenCalledTimes(pauseCallsBeforeTimer);
  });

  it("updates active progress safely and resets the rendered bar when the active item changes", () => {
    render(<VerticalVideoFeed items={items} controlsMode="reels" />);
    const firstSection = screen.getByLabelText("First video");
    const secondSection = screen.getByLabelText("Second video");
    const first = playerFor("First video");
    Object.defineProperties(first, {
      duration: { configurable: true, value: 10 },
      currentTime: { configurable: true, writable: true, value: 4 },
    });

    fireEvent.timeUpdate(first);
    expect(screen.getByTestId("reels-progress-one")).toHaveAttribute("aria-valuenow", "40");
    expect(screen.getByTestId("reels-progress-one").firstElementChild).toHaveStyle("transform: scaleX(0.4)");

    Object.defineProperty(first, "duration", { configurable: true, value: 0 });
    fireEvent.durationChange(first);
    expect(screen.getByTestId("reels-progress-one")).toHaveAttribute("aria-valuenow", "0");

    Object.defineProperty(first, "duration", { configurable: true, value: Number.NaN });
    fireEvent.durationChange(first);
    expect(screen.getByTestId("reels-progress-one")).toHaveAttribute("aria-valuenow", "0");

    act(() => observerFor(firstSection).trigger([
      { target: firstSection, ratio: 0 },
      { target: secondSection, ratio: 1 },
    ]));
    expect(screen.getByTestId("reels-progress-two")).toHaveAttribute("aria-valuenow", "0");
    expect(screen.queryByTestId("reels-progress-one")).not.toBeInTheDocument();
  });

  it("places Reels metadata above a transparent non-seekable progress layer without changing cover video", () => {
    render(<VerticalVideoFeed items={items} controlsMode="reels" hasBottomNavigation />);
    const layout = screen.getByTestId("reels-bottom-layout-one");
    const metadata = screen.getByTestId("reels-metadata-one");
    const glassZone = screen.getByTestId("reels-progress-glass-one");
    const progress = screen.getByTestId("reels-progress-one");

    expect(playerFor("First video")).toHaveClass("object-cover");
    expect(playerFor("First video")).not.toHaveClass("reels-progress-glass-zone");
    expect(layout).toContainElement(metadata);
    expect(layout).toContainElement(glassZone);
    expect(glassZone).toContainElement(progress);
    expect(glassZone).toHaveClass("reels-progress-glass-zone", "pointer-events-none");
    expect(glassZone).not.toHaveClass("reels-bottom-glass-backdrop");
    expect(metadata.compareDocumentPosition(glassZone) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(progress).not.toHaveAttribute("tabindex");
  });

  it("keeps bottom navigation pointer events outside the Reels gesture recognizer", () => {
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    render(
      <>
        <VerticalVideoFeed items={items} controlsMode="reels" hasBottomNavigation />
        <AppBottomNavigation activeRoute="offline" withReelsGlassBackdrop />
      </>,
    );
    const video = playerFor("First video");
    fireEvent.canPlay(video);
    pause.mockClear();

    const navigationLink = screen.getByRole("link", { name: "Главная" });
    expect(screen.getByTestId("reels-bottom-glass-backdrop")).toHaveAttribute("aria-hidden", "true");
    fireEvent.pointerDown(navigationLink, { button: 0, clientX: 50, clientY: 190, isPrimary: true, pointerId: 10 });
    fireEvent.pointerUp(navigationLink, { button: 0, clientX: 50, clientY: 190, isPrimary: true, pointerId: 10 });
    advanceHold();

    expect(pause).not.toHaveBeenCalled();
    expect(screen.getByTestId("reels-controls-one")).toHaveClass("opacity-0");
    expect(video.playbackRate).toBe(1);
  });

});

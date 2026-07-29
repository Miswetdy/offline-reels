// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VerticalVideoFeed, type VerticalVideoFeedItem } from "../components/vertical-video-feed";

const items: VerticalVideoFeedItem[] = [
  { id: "one", title: "First video", mediaUrl: "https://media.test/one.mp4", subtitle: "12 bytes" },
  { id: "two", title: "Second video", mediaUrl: "https://media.test/two.mp4" },
  { id: "three", title: "Third video", mediaUrl: "https://media.test/three.mp4" },
];

const fiveItems: VerticalVideoFeedItem[] = [
  ...items,
  { id: "four", title: "Fourth video", mediaUrl: "https://media.test/four.mp4" },
  { id: "five", title: "Fifth video", mediaUrl: "https://media.test/five.mp4" },
];

type TriggerEntry = { target: Element; ratio: number };

class MockIntersectionObserver {
  static instances: MockIntersectionObserver[] = [];

  readonly observe = vi.fn();
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

function sourcedPlayerCount(): number {
  return document.querySelectorAll("video[src]").length;
}

function setRect(element: Element, top: number, height = 100) {
  Object.defineProperty(element, "getBoundingClientRect", {
    configurable: true,
    value: () => ({ top, height }),
  });
}

beforeEach(() => {
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

describe("VerticalVideoFeed", () => {
  it("renders optional per-item actions and reports active item changes", async () => {
    const onActiveItemChange = vi.fn();
    render(
      <VerticalVideoFeed
        items={items}
        onActiveItemChange={onActiveItemChange}
        renderActions={(item) => <button type="button">Save {item.title}</button>}
      />,
    );

    const first = await screen.findByLabelText("First video");
    const third = screen.getByLabelText("Third video");
    expect(screen.getByRole("button", { name: "Save First video" })).toBeInTheDocument();
    await waitFor(() => expect(onActiveItemChange).toHaveBeenLastCalledWith(items[0]));

    observerFor(first).trigger([{ target: third, ratio: 0.9 }]);

    await waitFor(() => expect(onActiveItemChange).toHaveBeenLastCalledWith(items[2]));
    expect(playerFor("Third video")).toHaveAttribute("src", items[2].mediaUrl);
    expect(playerFor("First video")).not.toHaveAttribute("src");
    expect(playerFor("Second video")).toHaveAttribute("src", items[1].mediaUrl);
  });

  it("keeps active plus next sources at the first item and uses the shared mute state", async () => {
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    render(<VerticalVideoFeed items={items} />);
    const first = await screen.findByLabelText("First video");
    const second = screen.getByLabelText("Second video");
    const third = screen.getByLabelText("Third video");

    await waitFor(() => expect(playerFor("First video")).toHaveAttribute("src", items[0].mediaUrl));
    expect(playerFor("First video")).toHaveAttribute("playsinline");
    expect(playerFor("Second video")).toHaveAttribute("src", items[1].mediaUrl);
    expect(playerFor("Third video")).not.toHaveAttribute("src");
    expect(sourcedPlayerCount()).toBe(2);
    fireEvent.click(screen.getByRole("button", { name: "Turn sound on" }));
    expect(playerFor("First video")).toHaveProperty("muted", false);
    expect(playerFor("Third video")).toHaveProperty("muted", false);

    observerFor(first).trigger([{ target: second, ratio: 0.9 }]);
    await waitFor(() => expect(playerFor("Second video")).toHaveAttribute("preload", "auto"));
    await waitFor(() => expect(playerFor("Third video")).toHaveAttribute("src", items[2].mediaUrl));
    expect(playerFor("First video")).toHaveAttribute("src", items[0].mediaUrl);
    expect(playerFor("First video")).toHaveAttribute("preload", "metadata");
    expect(playerFor("Third video")).toHaveAttribute("preload", "metadata");
    expect(sourcedPlayerCount()).toBe(3);
    expect(pause.mock.contexts).toEqual(expect.arrayContaining([playerFor("First video"), playerFor("Third video")]));
  });

  it("keeps previous plus active sources at the last item", async () => {
    render(<VerticalVideoFeed items={items} />);
    const first = await screen.findByLabelText("First video");
    const third = screen.getByLabelText("Third video");

    observerFor(first).trigger([{ target: third, ratio: 1 }]);

    await waitFor(() => expect(playerFor("Third video")).toHaveAttribute("src", items[2].mediaUrl));
    expect(playerFor("Second video")).toHaveAttribute("src", items[1].mediaUrl);
    expect(playerFor("First video")).not.toHaveAttribute("src");
    expect(sourcedPlayerCount()).toBe(2);
  });

  it("restarts a video before playback only when it becomes active again", async () => {
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    const playSnapshots: Array<{ video: HTMLMediaElement; currentTime: number }> = [];
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function play(this: HTMLMediaElement) {
      playSnapshots.push({ video: this, currentTime: this.currentTime });
      return Promise.resolve();
    });
    render(<VerticalVideoFeed items={items} />);
    const firstSection = await screen.findByLabelText("First video");
    const secondSection = screen.getByLabelText("Second video");
    const first = playerFor("First video");
    const second = playerFor("Second video");

    fireEvent.canPlay(first);
    expect(playSnapshots).toContainEqual({ video: first, currentTime: 0 });
    first.currentTime = 7;
    pause.mockClear();

    observerFor(firstSection).trigger([{ target: secondSection, ratio: 0.9 }]);
    await waitFor(() => expect(second).toHaveAttribute("preload", "auto"));
    expect(pause.mock.contexts).toContain(first);
    fireEvent.canPlay(second);
    expect(playSnapshots).toContainEqual({ video: second, currentTime: 0 });
    second.currentTime = 4;

    observerFor(firstSection).trigger([
      { target: firstSection, ratio: 0.9 },
      { target: secondSection, ratio: 0 },
    ]);
    await waitFor(() => expect(first).toHaveAttribute("preload", "auto"));
    fireEvent.canPlay(first);
    expect(playSnapshots).toContainEqual({ video: first, currentTime: 0 });
    expect(first.currentTime).toBe(0);
    first.currentTime = 6;

    observerFor(firstSection).trigger([
      { target: firstSection, ratio: 0 },
      { target: secondSection, ratio: 0.9 },
    ]);
    await waitFor(() => expect(second).toHaveAttribute("preload", "auto"));
    fireEvent.canPlay(second);
    expect(playSnapshots).toContainEqual({ video: second, currentTime: 0 });
    expect(second.currentTime).toBe(0);
    expect(sourcedPlayerCount()).toBe(3);
  });

  it("does not reset the active video for mute or item updates", async () => {
    const view = render(<VerticalVideoFeed items={items} />);
    await screen.findByLabelText("First video");
    const first = playerFor("First video");
    fireEvent.canPlay(first);
    first.currentTime = 7;

    fireEvent.click(screen.getByRole("button", { name: "Turn sound on" }));
    expect(first.currentTime).toBe(7);

    view.rerender(<VerticalVideoFeed items={[...items]} />);
    expect(first.currentTime).toBe(7);
  });

  it("ignores stale canplay callbacks after a rapid active-video transition", async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    render(<VerticalVideoFeed items={items} />);
    const firstSection = await screen.findByLabelText("First video");
    const secondSection = screen.getByLabelText("Second video");
    const first = playerFor("First video");
    const second = playerFor("Second video");
    let firstCurrentTime = 7;
    const setFirstCurrentTime = vi.fn((value: number) => {
      firstCurrentTime = value;
    });
    Object.defineProperty(first, "currentTime", {
      configurable: true,
      get: () => firstCurrentTime,
      set: setFirstCurrentTime,
    });

    observerFor(firstSection).trigger([{ target: secondSection, ratio: 0.9 }]);
    await waitFor(() => expect(second).toHaveAttribute("preload", "auto"));
    fireEvent.canPlay(first);
    expect(firstCurrentTime).toBe(7);
    expect(setFirstCurrentTime).not.toHaveBeenCalled();
    expect(play.mock.contexts).not.toContain(first);

    fireEvent.canPlay(second);
    expect(play.mock.contexts).toContain(second);
    expect(play.mock.contexts).not.toContain(first);
  });

  it("pauses an obsolete play promise after a rapid active-video transition", async () => {
    let resolveFirstPlay: (() => void) | undefined;
    const firstPlay = new Promise<void>((resolve) => {
      resolveFirstPlay = resolve;
    });
    let first: HTMLVideoElement;
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function play(this: HTMLMediaElement) {
      return this === first ? firstPlay : Promise.resolve();
    });
    render(<VerticalVideoFeed items={items} />);
    const firstSection = await screen.findByLabelText("First video");
    const secondSection = screen.getByLabelText("Second video");
    first = playerFor("First video");
    const second = playerFor("Second video");

    fireEvent.canPlay(first);
    observerFor(firstSection).trigger([{ target: secondSection, ratio: 0.9 }]);
    await waitFor(() => expect(second).toHaveAttribute("preload", "auto"));
    fireEvent.canPlay(second);
    pause.mockClear();
    resolveFirstPlay?.();

    await waitFor(() => expect(pause.mock.contexts).toContain(first));
    expect(play.mock.contexts).toContain(second);
  });

  it("releases distant sources across rapid active changes and keeps a valid active item after removal", async () => {
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    const view = render(<VerticalVideoFeed items={fiveItems} />);
    const first = await screen.findByLabelText("First video");
    const second = screen.getByLabelText("Second video");
    const third = screen.getByLabelText("Third video");
    const fourth = screen.getByLabelText("Fourth video");
    const fifth = screen.getByLabelText("Fifth video");

    observerFor(first).trigger([{ target: second, ratio: 0.9 }, { target: third, ratio: 0 }]);
    observerFor(first).trigger([{ target: second, ratio: 0 }, { target: third, ratio: 1 }]);
    observerFor(first).trigger([{ target: third, ratio: 0 }, { target: fourth, ratio: 1 }]);
    await waitFor(() => expect(playerFor("Fourth video")).toHaveAttribute("src", fiveItems[3].mediaUrl));
    expect(playerFor("First video")).not.toHaveAttribute("src");
    expect(playerFor("Second video")).not.toHaveAttribute("src");
    expect(playerFor("Third video")).toHaveAttribute("src", items[2].mediaUrl);
    expect(playerFor("Fifth video")).toHaveAttribute("src", fiveItems[4].mediaUrl);
    expect(sourcedPlayerCount()).toBe(3);

    view.rerender(<VerticalVideoFeed items={fiveItems.slice(3)} />);
    await waitFor(() => expect(playerFor("Fourth video")).toHaveAttribute("src", fiveItems[3].mediaUrl));
    expect(playerFor("Fifth video")).toHaveAttribute("src", fiveItems[4].mediaUrl);
    expect(sourcedPlayerCount()).toBe(2);

    view.rerender(<VerticalVideoFeed items={[]} emptyState={<main>Offline library is empty.</main>} />);
    await screen.findByText("Offline library is empty.");
    expect(document.querySelectorAll("video[src]")).toHaveLength(0);
    expect(pause).toHaveBeenCalled();
  });

  it("pauses media for visibility and page lifecycle events without autoplaying on restore", async () => {
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    render(<VerticalVideoFeed items={items} />);
    await screen.findByLabelText("First video");
    pause.mockClear();
    const playCallsBeforeRestore = play.mock.calls.length;

    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
    document.dispatchEvent(new Event("visibilitychange"));
    expect(pause).toHaveBeenCalled();

    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
    document.dispatchEvent(new Event("visibilitychange"));
    window.dispatchEvent(new Event("pageshow"));
    expect(play).toHaveBeenCalledTimes(playCallsBeforeRestore);

    pause.mockClear();
    window.dispatchEvent(new Event("pagehide"));
    expect(pause).toHaveBeenCalled();
  });

  it("turns a media transport error into a terminal local state without retrying the broken source", async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    const load = vi.spyOn(HTMLMediaElement.prototype, "load");
    render(<VerticalVideoFeed items={items} />);
    await screen.findByLabelText("First video");
    const first = playerFor("First video");
    const callsBeforeError = play.mock.calls.length;
    const loadsBeforeError = load.mock.calls.length;
    expect(first).toHaveAttribute("src", items[0].mediaUrl);
    expect(first).toHaveAttribute("aria-busy", "true");

    fireEvent.error(first);

    expect(await screen.findByRole("alert")).toHaveTextContent("This video could not be played.");
    expect(first).not.toHaveAttribute("src");
    expect(first).toHaveAttribute("aria-busy", "false");
    expect(load).toHaveBeenCalledTimes(loadsBeforeError + 1);
    expect(playerFor("Second video")).toHaveAttribute("src", items[1].mediaUrl);
    expect(play).toHaveBeenCalledTimes(callsBeforeError);
    expect(sourcedPlayerCount()).toBe(1);

    fireEvent.scroll(screen.getByLabelText("Video feed"));
    await waitFor(() => expect(playerFor("First video")).not.toHaveAttribute("src"));
    expect(load).toHaveBeenCalledTimes(loadsBeforeError + 1);
  });

  it("keeps neighboring media usable after an errored active item is replaced", async () => {
    const view = render(<VerticalVideoFeed items={items} />);
    const first = await screen.findByLabelText("First video");
    const second = screen.getByLabelText("Second video");
    fireEvent.error(playerFor("First video"));
    await screen.findByRole("alert");

    observerFor(first).trigger([{ target: second, ratio: 1 }]);
    await waitFor(() => expect(playerFor("Second video")).toHaveAttribute("src", items[1].mediaUrl));
    await waitFor(() => expect(playerFor("Third video")).toHaveAttribute("src", items[2].mediaUrl));
    expect(playerFor("First video")).not.toHaveAttribute("src");
    expect(sourcedPlayerCount()).toBe(2);

    view.rerender(<VerticalVideoFeed items={items} />);
    await waitFor(() => expect(playerFor("Second video")).toHaveAttribute("src", items[1].mediaUrl));
    expect(playerFor("First video")).not.toHaveAttribute("src");
  });

  it("uses the center fallback and cleans observer and scheduled animation frames on unmount", async () => {
    let frame: FrameRequestCallback | undefined;
    const requestAnimationFrame = vi.fn((callback: FrameRequestCallback) => {
      frame = callback;
      return 17;
    });
    const cancelAnimationFrame = vi.fn();
    vi.stubGlobal("requestAnimationFrame", requestAnimationFrame);
    vi.stubGlobal("cancelAnimationFrame", cancelAnimationFrame);
    const view = render(<VerticalVideoFeed items={items} />);
    const feed = await screen.findByLabelText("Video feed");
    const first = screen.getByLabelText("First video");
    const second = screen.getByLabelText("Second video");
    const third = screen.getByLabelText("Third video");
    setRect(feed, 0);
    setRect(first, -200);
    setRect(second, -100);
    setRect(third, 0);

    fireEvent.scroll(feed);
    expect(requestAnimationFrame).toHaveBeenCalledTimes(1);
    view.unmount();

    expect(observerFor(first).disconnect).toHaveBeenCalledTimes(1);
    expect(cancelAnimationFrame).toHaveBeenCalledWith(17);
    expect(frame).toBeDefined();
  });

  it("renders the supplied empty state and reports no active item", async () => {
    const onActiveItemChange = vi.fn();
    render(
      <VerticalVideoFeed
        items={[]}
        emptyState={<main>Offline library is empty.</main>}
        onActiveItemChange={onActiveItemChange}
      />,
    );

    expect(screen.getByText("Offline library is empty.")).toBeInTheDocument();
    await waitFor(() => expect(onActiveItemChange).toHaveBeenLastCalledWith(null));
    expect(screen.queryByLabelText("Video feed")).not.toBeInTheDocument();
  });

});

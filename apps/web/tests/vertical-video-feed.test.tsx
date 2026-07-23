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
    expect(playerFor("Second video")).not.toHaveAttribute("src");
  });

  it("keeps active plus next sources, shared mute state, and pauses inactive players", async () => {
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    render(<VerticalVideoFeed items={items} />);
    const first = await screen.findByLabelText("First video");
    const second = screen.getByLabelText("Second video");
    const third = screen.getByLabelText("Third video");

    await waitFor(() => expect(playerFor("First video")).toHaveAttribute("src", items[0].mediaUrl));
    expect(playerFor("Second video")).toHaveAttribute("src", items[1].mediaUrl);
    expect(playerFor("Third video")).not.toHaveAttribute("src");
    fireEvent.click(screen.getByRole("button", { name: "Turn sound on" }));
    expect(playerFor("First video")).toHaveProperty("muted", false);
    expect(playerFor("Third video")).toHaveProperty("muted", false);

    observerFor(first).trigger([{ target: second, ratio: 0.9 }]);
    await waitFor(() => expect(playerFor("Second video")).toHaveAttribute("preload", "auto"));
    expect(playerFor("Third video")).toHaveAttribute("src", items[2].mediaUrl);
    expect(playerFor("First video")).not.toHaveAttribute("src");
    expect(pause).toHaveBeenCalled();
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

  it("resolves temporary media only for active plus next and revokes it when the window changes or unmounts", async () => {
    const revoke = new Map(items.map((item) => [item.id, vi.fn()]));
    const resolveMediaSource = vi.fn(async (item: VerticalVideoFeedItem) => ({
      url: `blob:${item.id}`,
      revoke: revoke.get(item.id)!,
    }));
    const view = render(<VerticalVideoFeed items={items} resolveMediaSource={resolveMediaSource} />);
    const first = await screen.findByLabelText("First video");
    const third = screen.getByLabelText("Third video");

    await waitFor(() => expect(resolveMediaSource).toHaveBeenCalledTimes(2));
    expect(playerFor("First video")).toHaveAttribute("src", "blob:one");
    expect(playerFor("Second video")).toHaveAttribute("src", "blob:two");
    expect(playerFor("Third video")).not.toHaveAttribute("src");

    observerFor(first).trigger([{ target: third, ratio: 0.9 }]);
    await waitFor(() => expect(resolveMediaSource).toHaveBeenCalledTimes(3));
    expect(revoke.get("one")).toHaveBeenCalledTimes(1);
    expect(playerFor("Third video")).toHaveAttribute("src", "blob:three");
    view.unmount();
    expect(revoke.get("two")).toHaveBeenCalledTimes(1);
    expect(revoke.get("three")).toHaveBeenCalledTimes(1);
  });
});

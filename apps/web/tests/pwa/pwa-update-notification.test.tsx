// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { useSerwist } = vi.hoisted(() => ({ useSerwist: vi.fn() }));

vi.mock("@serwist/turbopack/react", () => ({ useSerwist }));

import { PwaUpdateNotification } from "../../app/pwa-update-notification";

type LifecycleEvent = { type: "installing" | "installed" | "waiting" | "controlling" };

class FakeSerwist {
  readonly messageSkipWaiting = vi.fn();
  private readonly listeners = new Map<LifecycleEvent["type"], Set<(event: LifecycleEvent) => void>>();

  addEventListener(type: LifecycleEvent["type"], listener: (event: LifecycleEvent) => void) {
    const listeners = this.listeners.get(type) ?? new Set();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }

  removeEventListener(type: LifecycleEvent["type"], listener: (event: LifecycleEvent) => void) {
    this.listeners.get(type)?.delete(listener);
  }

  emit(type: LifecycleEvent["type"]) {
    for (const listener of this.listeners.get(type) ?? []) listener({ type });
  }
}

function renderNotification(serwist: FakeSerwist | null, onReload = vi.fn()) {
  useSerwist.mockReturnValue({ serwist });
  render(<PwaUpdateNotification onReload={onReload} />);
  return onReload;
}

function emitLifecycleEvent(serwist: FakeSerwist, type: LifecycleEvent["type"]) {
  act(() => serwist.emit(type));
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("PwaUpdateNotification", () => {
  it("shows an update already waiting during initial registration", () => {
    const serwist = new FakeSerwist();
    renderNotification(serwist);

    emitLifecycleEvent(serwist, "waiting");

    expect(screen.getByRole("status")).toHaveTextContent("Доступна новая версия");
    expect(screen.getByRole("button", { name: "Обновить" })).toBeEnabled();
  });

  it("shows an update only after Serwist moves a discovered update through installing and installed to waiting", () => {
    const serwist = new FakeSerwist();
    renderNotification(serwist);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    emitLifecycleEvent(serwist, "installing");
    emitLifecycleEvent(serwist, "installed");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    emitLifecycleEvent(serwist, "waiting");

    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("sends the waiting-worker activation command only after the user clicks", () => {
    const serwist = new FakeSerwist();
    renderNotification(serwist);
    emitLifecycleEvent(serwist, "waiting");

    expect(serwist.messageSkipWaiting).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Обновить" }));

    expect(serwist.messageSkipWaiting).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Обновить" })).toBeDisabled();
  });

  it("reloads once only after a user-requested activation changes the controller", () => {
    const serwist = new FakeSerwist();
    const onReload = renderNotification(serwist);
    emitLifecycleEvent(serwist, "waiting");

    emitLifecycleEvent(serwist, "controlling");
    expect(onReload).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Обновить" }));
    emitLifecycleEvent(serwist, "controlling");
    emitLifecycleEvent(serwist, "controlling");

    expect(onReload).toHaveBeenCalledTimes(1);
  });

  it("does not expose an update UI or access offline storage without a waiting worker", () => {
    const serwist = new FakeSerwist();
    const cacheOpen = vi.fn();
    const indexedDbOpen = vi.fn();
    vi.stubGlobal("caches", { open: cacheOpen });
    vi.stubGlobal("indexedDB", { open: indexedDbOpen });
    renderNotification(serwist);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(cacheOpen).not.toHaveBeenCalled();
    expect(indexedDbOpen).not.toHaveBeenCalled();
  });
});

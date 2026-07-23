// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NetworkStatusIndicator } from "../components/network-status-indicator";
import { getInitialNetworkStatus } from "../hooks/use-network-status";

function setOnline(value: boolean) {
  Object.defineProperty(window.navigator, "onLine", { configurable: true, value });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("NetworkStatusIndicator", () => {
  it("is safe to import without browser APIs", async () => {
    await expect(import("../hooks/use-network-status")).resolves.toBeDefined();
  });

  it("updates from online and offline browser events", () => {
    setOnline(false);
    render(<NetworkStatusIndicator offlineMessage="Офлайн" onlineMessage="Онлайн" />);
    expect(screen.getByTestId("network-status")).toHaveTextContent("Офлайн");

    setOnline(true);
    fireEvent(window, new Event("online"));
    expect(screen.getByTestId("network-status")).toHaveTextContent("Онлайн");
  });

  it("reads the browser network state synchronously on the initial client render", () => {
    setOnline(false);
    expect(getInitialNetworkStatus()).toBe(false);
  });
});

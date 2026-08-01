// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AppBottomNavigation } from "../components/app-bottom-navigation";

afterEach(cleanup);

describe("AppBottomNavigation", () => {
  it("uses the canonical dashboard as the active main destination", () => {
    render(<AppBottomNavigation activeRoute="home" />);

    const navigation = screen.getByRole("navigation", { name: "Основная навигация" });
    const home = screen.getByRole("link", { name: "Главная" });
    const offline = screen.getByRole("link", { name: "Рилсы" });

    expect(navigation).toHaveClass("app-bottom-navigation", "app-bottom-navigation--floating");
    expect(home).toHaveAttribute("href", "/");
    expect(home).toHaveAttribute("aria-current", "page");
    expect(offline).toHaveAttribute("href", "/offline");
    expect(offline).not.toHaveAttribute("aria-current");
    expect(home.querySelector("svg[aria-hidden='true']")).toBeInTheDocument();
    expect(offline.querySelector("svg[aria-hidden='true']")).toBeInTheDocument();
  });

  it("marks only Reels active on /offline", () => {
    render(<AppBottomNavigation activeRoute="offline" />);

    expect(screen.getByRole("link", { name: "Главная" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "Рилсы" })).toHaveAttribute("aria-current", "page");
  });

  it("adds the single pointer-inert Reels backdrop only when explicitly requested", () => {
    render(<AppBottomNavigation activeRoute="offline" withReelsGlassBackdrop />);

    expect(screen.getByTestId("reels-bottom-glass-backdrop")).toHaveClass("reels-bottom-glass-backdrop");
  });
});

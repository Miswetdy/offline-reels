// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AppBottomNavigation } from "../components/app-bottom-navigation";

afterEach(cleanup);

describe("AppBottomNavigation", () => {
  it("marks the main and download destination active on /videos", () => {
    render(<AppBottomNavigation activeRoute="videos" />);

    const navigation = screen.getByRole("navigation", { name: "Основная навигация" });
    const videos = screen.getByRole("link", { name: "Главная и загрузка" });
    const offline = screen.getByRole("link", { name: "Офлайн-библиотека" });

    expect(navigation).toHaveClass("app-bottom-navigation");
    expect(navigation).toHaveClass("app-bottom-navigation--floating");
    expect(navigation).toHaveAttribute("data-testid", "app-bottom-navigation");
    expect(videos).toHaveAttribute("href", "/videos");
    expect(videos).toHaveAttribute("aria-current", "page");
    expect(offline).toHaveAttribute("href", "/offline");
    expect(offline).not.toHaveAttribute("aria-current");
    expect(videos.querySelector("svg[aria-hidden='true']")).toBeInTheDocument();
    expect(offline.querySelector("svg[aria-hidden='true']")).toBeInTheDocument();
    expect(navigation).not.toHaveTextContent("🏠");
    expect(navigation).not.toHaveTextContent("▶");
  });

  it("marks only the offline library destination active on /offline", () => {
    render(<AppBottomNavigation activeRoute="offline" />);

    expect(screen.queryByTestId("reels-bottom-glass-backdrop")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Главная и загрузка" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "Офлайн-библиотека" })).toHaveAttribute("aria-current", "page");
  });

  it("adds the single pointer-inert Reels backdrop only when explicitly requested", () => {
    render(<AppBottomNavigation activeRoute="offline" withReelsGlassBackdrop />);

    const backdrop = screen.getByTestId("reels-bottom-glass-backdrop");
    expect(backdrop).toHaveClass("reels-bottom-glass-backdrop");
    expect(backdrop).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByRole("link", { name: "Офлайн-библиотека" })).toHaveAttribute("aria-current", "page");
  });
});

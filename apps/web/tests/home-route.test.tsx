// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../components/library-dashboard", () => ({
  LibraryDashboard: () => <main data-testid="library-dashboard">Dashboard</main>,
}));

import HomePage from "../app/page";

describe("canonical home route", () => {
  it("renders the library dashboard at /", () => {
    render(<HomePage />);
    expect(screen.getByTestId("library-dashboard")).toBeInTheDocument();
  });
});

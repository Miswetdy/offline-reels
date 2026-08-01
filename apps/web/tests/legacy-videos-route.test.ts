import { describe, expect, it, vi } from "vitest";

const redirect = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ redirect }));

import VideosPage from "../app/videos/page";

describe("legacy /videos route", () => {
  it("redirects to the canonical dashboard", () => {
    VideosPage();
    expect(redirect).toHaveBeenCalledWith("/");
  });
});

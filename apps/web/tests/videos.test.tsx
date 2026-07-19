// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { VideoList } from "../components/video-list";
import * as videosApi from "../lib/api/videos";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("VideoList", () => {
  it("shows a loading state", () => {
    vi.spyOn(videosApi, "getVideos").mockReturnValue(new Promise(() => {}));
    render(<VideoList />);
    expect(screen.getByText("Loading videos…")).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    vi.spyOn(videosApi, "getVideos").mockResolvedValue([]);
    render(<VideoList />);
    expect(await screen.findByText("No videos are available yet.")).toBeInTheDocument();
  });

  it("shows an error state", async () => {
    vi.spyOn(videosApi, "getVideos").mockRejectedValue(new Error("unavailable"));
    render(<VideoList />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load videos.");
  });

  it("renders a player through the Backend API", async () => {
    vi.spyOn(videosApi, "getVideos").mockResolvedValue([
      {
        id: "video-id",
        title: "Test video",
        content_type: "video/mp4",
        byte_size: 12,
        created_at: "2026-07-19T00:00:00Z",
      },
    ]);
    render(<VideoList />);

    const player = await screen.findByText("Test video");
    await waitFor(() => expect(player).toBeInTheDocument());
    expect(screen.getByLabelText("Videos").querySelector("video")).toHaveAttribute(
      "src",
      "http://localhost:8000/videos/video-id/stream",
    );
  });
});

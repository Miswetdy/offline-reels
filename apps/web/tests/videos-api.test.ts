import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getVideoStreamUrl, getVideos } from "../lib/api/videos";

const originalApiUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

beforeEach(() => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "https://api.example.test";
});

afterEach(() => {
  if (originalApiUrl === undefined) delete process.env.NEXT_PUBLIC_API_BASE_URL;
  else process.env.NEXT_PUBLIC_API_BASE_URL = originalApiUrl;
});

describe("videos API client", () => {
  it("does not allow a backend catalog response to enter browser HTTP caches", async () => {
    const fetchImplementation = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], next_cursor: null }), { status: 200 }),
    );

    await getVideos({}, fetchImplementation);

    expect(fetchImplementation).toHaveBeenCalledWith(
      "https://api.example.test/videos?limit=5",
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("classifies a fetch rejection separately from an HTTP API error", async () => {
    const networkFailure = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    const httpFailure = vi.fn().mockResolvedValue(new Response(null, { status: 500 }));

    await expect(getVideos({}, networkFailure)).rejects.toMatchObject({
      name: "VideoCatalogError",
      kind: "network",
    });
    await expect(getVideos({}, httpFailure)).rejects.toMatchObject({
      name: "VideoCatalogError",
      kind: "http",
    });
  });

  it("requires a configured absolute public API URL instead of assuming browser localhost", () => {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;

    expect(() => getVideoStreamUrl("video-one")).toThrow("NEXT_PUBLIC_API_BASE_URL is not configured");
  });

  it("uses an explicitly configured non-local origin for stream URLs", () => {
    expect(getVideoStreamUrl("video-one")).toBe("https://api.example.test/videos/video-one/stream");
  });
});

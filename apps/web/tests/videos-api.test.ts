import { describe, expect, it, vi } from "vitest";

import { getVideos } from "../lib/api/videos";

describe("videos API client", () => {
  it("does not allow a backend catalog response to enter browser HTTP caches", async () => {
    const fetchImplementation = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], next_cursor: null }), { status: 200 }),
    );

    await getVideos({}, fetchImplementation);

    expect(fetchImplementation).toHaveBeenCalledWith(
      "http://localhost:8000/videos?limit=5",
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
});

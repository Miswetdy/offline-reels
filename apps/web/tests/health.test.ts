import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { checkBackendLive } from "../lib/api/health";

const originalApiUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

beforeEach(() => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "https://api.example.test";
});

afterEach(() => {
  if (originalApiUrl === undefined) delete process.env.NEXT_PUBLIC_API_BASE_URL;
  else process.env.NEXT_PUBLIC_API_BASE_URL = originalApiUrl;
});

describe("checkBackendLive", () => {
  it("returns available for a successful live endpoint", async () => {
    const fetchImplementation = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));

    await expect(checkBackendLive(fetchImplementation)).resolves.toBe("available");
    expect(fetchImplementation).toHaveBeenCalledWith(
      "https://api.example.test/health/live",
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("preserves an API path prefix for the live endpoint", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "https://staging.example.ts.net/api";
    const fetchImplementation = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));

    await expect(checkBackendLive(fetchImplementation)).resolves.toBe("available");
    expect(fetchImplementation).toHaveBeenCalledWith(
      "https://staging.example.ts.net/api/health/live",
      expect.anything(),
    );
  });

  it("returns unavailable when the endpoint cannot be reached", async () => {
    const fetchImplementation = vi.fn().mockRejectedValue(new Error("network unavailable"));

    await expect(checkBackendLive(fetchImplementation)).resolves.toBe("unavailable");
  });

  it("reports a missing public API URL as configuration rather than reachability failure", async () => {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;

    await expect(checkBackendLive()).resolves.toBe("misconfigured");
  });
});

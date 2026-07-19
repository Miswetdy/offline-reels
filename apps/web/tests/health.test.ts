import { describe, expect, it, vi } from "vitest";

import { checkBackendLive } from "../lib/api/health";

describe("checkBackendLive", () => {
  it("returns available for a successful live endpoint", async () => {
    const fetchImplementation = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));

    await expect(checkBackendLive(fetchImplementation)).resolves.toBe("available");
  });

  it("returns unavailable when the endpoint cannot be reached", async () => {
    const fetchImplementation = vi.fn().mockRejectedValue(new Error("network unavailable"));

    await expect(checkBackendLive(fetchImplementation)).resolves.toBe("unavailable");
  });
});

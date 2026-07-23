import { describe, expect, it } from "vitest";

import { GET, serwistRouteOptions } from "../app/serwist/[path]/route";
import { OFFLINE_SHELL_URL } from "../lib/pwa/offline-shell-precache";

describe("Serwist worker route", () => {
  it("exports the dynamic worker handler", () => {
    expect(GET).toBeTypeOf("function");
  });

  it("passes the revisioned offline shell to the worker manifest input", () => {
    expect(serwistRouteOptions.additionalPrecacheEntries).toEqual([
      { url: OFFLINE_SHELL_URL, revision: expect.stringMatching(/^[a-f0-9]{64}$/) },
    ]);
  });
});

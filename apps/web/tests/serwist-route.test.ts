import { describe, expect, it } from "vitest";

import { GET, serwistRouteOptions } from "../app/serwist/[path]/route";
import { HOME_SHELL_URL, OFFLINE_SHELL_URL, WEB_MANIFEST_URL } from "../lib/pwa/offline-shell-precache";

describe("Serwist worker route", () => {
  it("exports the dynamic worker handler", () => {
    expect(GET).toBeTypeOf("function");
  });

  it("passes only the dashboard, Reels, and manifest shells to the worker", () => {
    expect(serwistRouteOptions.additionalPrecacheEntries).toEqual([
      { url: HOME_SHELL_URL, revision: expect.stringMatching(/^[a-f0-9]{64}$/) },
      { url: OFFLINE_SHELL_URL, revision: expect.stringMatching(/^[a-f0-9]{64}$/) },
      { url: WEB_MANIFEST_URL, revision: expect.stringMatching(/^[a-f0-9]{64}$/) },
    ]);
  });
});

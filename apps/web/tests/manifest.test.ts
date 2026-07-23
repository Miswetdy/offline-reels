import { describe, expect, it } from "vitest";

import manifest from "../app/manifest";

describe("PWA manifest", () => {
  it("starts the installed application at the offline library", () => {
    expect(manifest().start_url).toBe("/offline");
  });
});

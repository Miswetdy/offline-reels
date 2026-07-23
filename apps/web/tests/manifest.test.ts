import { describe, expect, it } from "vitest";

import manifest from "../app/manifest";

describe("PWA manifest", () => {
  it("starts the installed application at the offline library", () => {
    expect(manifest()).toMatchObject({
      start_url: "/offline",
      display: "standalone",
      background_color: "#f8fafc",
      theme_color: "#0f172a",
      icons: [{ src: "/icon.svg", type: "image/svg+xml" }],
    });
  });
});

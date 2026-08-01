import { describe, expect, it } from "vitest";

import manifest from "../app/manifest";

describe("PWA manifest", () => {
  it("starts the installed application at the canonical dashboard", () => {
    expect(manifest()).toMatchObject({
      id: "/",
      start_url: "/",
      scope: "/",
      display: "standalone",
      background_color: "#f8fafc",
      theme_color: "#0f172a",
      icons: [{ src: "/icon.svg", type: "image/svg+xml" }],
    });
  });
});

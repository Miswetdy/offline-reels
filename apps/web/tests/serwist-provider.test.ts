import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

describe("OfflineShellProvider", () => {
  it("does not wire a runtime launch redirect", () => {
    const providerSource = readFileSync(join(process.cwd(), "app", "serwist-provider.tsx"), "utf8");

    expect(providerSource).not.toMatch(/PwaLaunchGuard|pwa-launch-guard|router\.replace/);
    expect(existsSync(join(process.cwd(), "app", "pwa-launch-guard.tsx"))).toBe(false);
  });
});

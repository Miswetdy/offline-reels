import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: "stage8.fixture.spec.ts",
  timeout: 300_000,
  fullyParallel: false,
  forbidOnly: true,
  reporter: "list",
  outputDir: "test-results-stage8",
  use: {
    ...devices["iPhone 13"],
    browserName: "chromium",
    baseURL: process.env.STAGE8_E2E_ORIGIN,
    ignoreHTTPSErrors: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: {
      // Caddy issues an ephemeral internal certificate per disposable fixture.
      // Chromium otherwise rejects only the Service Worker script fetch before
      // the test can verify offline behavior.
      args: ["--ignore-certificate-errors"],
    },
  },
});

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: "stage9.fixture.spec.ts",
  timeout: 300_000,
  fullyParallel: false,
  forbidOnly: true,
  reporter: "list",
  outputDir: "test-results-stage9",
  use: {
    ...devices["iPhone 13"],
    browserName: "chromium",
    baseURL: process.env.STAGE9_E2E_ORIGIN,
    ignoreHTTPSErrors: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: { args: ["--ignore-certificate-errors"] },
    storageState: { cookies: [], origins: [] },
  },
});

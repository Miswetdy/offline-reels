import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { getApiBaseUrl, getApiUrl } from "../lib/api/config";

const originalApiUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

beforeEach(() => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "https://api.example.test";
});

afterEach(() => {
  if (originalApiUrl === undefined) delete process.env.NEXT_PUBLIC_API_BASE_URL;
  else process.env.NEXT_PUBLIC_API_BASE_URL = originalApiUrl;
});

describe("public API URL configuration", () => {
  it("resolves an explicit HTTPS API origin", () => {
    expect(getApiBaseUrl()).toBe("https://api.example.test");
  });

  it("preserves an explicit API path prefix when joining an endpoint", () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "https://staging.example.ts.net/api/";

    expect(getApiBaseUrl()).toBe("https://staging.example.ts.net/api");
    expect(getApiUrl("/videos")).toBe("https://staging.example.ts.net/api/videos");
  });

  it("does not silently fall back to localhost when configuration is absent", () => {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;

    expect(() => getApiBaseUrl()).toThrow("NEXT_PUBLIC_API_BASE_URL is not configured");
  });

  it("rejects non-public configuration shapes that could expose credentials or change request routing", () => {
    for (const value of ["api.example.test", "ftp://api.example.test", "https://token@example.test", "https://api.example.test?token=x"]) {
      process.env.NEXT_PUBLIC_API_BASE_URL = value;
      expect(() => getApiBaseUrl()).toThrow("NEXT_PUBLIC_API_BASE_URL");
    }
  });
});

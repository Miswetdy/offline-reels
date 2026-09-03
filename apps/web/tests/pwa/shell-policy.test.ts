import { describe, expect, it } from "vitest";

import {
  OFFLINE_MEDIA_CACHE_NAME,
  isExplicitApplicationShellPath,
  isExcludedFromShellCaching,
  selectOutdatedShellCaches,
  shouldUseOfflineNavigationFallback,
} from "../../lib/pwa/shell-policy";
import {
  HOME_SHELL_URL,
  OFFLINE_SHELL_URL,
  WEB_MANIFEST_URL,
  createApplicationShellPrecacheEntry,
  createApplicationShellPrecacheEntriesFromBuildInputs,
} from "../../lib/pwa/offline-shell-precache";

const applicationOrigin = "http://localhost:3000";

function request(method: string, pathOrUrl: string) {
  return { method, url: new URL(pathOrUrl, applicationOrigin), applicationOrigin };
}

describe("application-shell cache policy", () => {
  it("uses the canonical dashboard as the revisioned navigation fallback", () => {
    const first = createApplicationShellPrecacheEntry(HOME_SHELL_URL, "dashboard shell");
    const changed = createApplicationShellPrecacheEntry(HOME_SHELL_URL, "updated dashboard shell");

    expect(first).toEqual({ url: HOME_SHELL_URL, revision: expect.any(String) });
    expect(first.revision).toHaveLength(64);
    expect(changed.revision).not.toBe(first.revision);
  });

  it("allows only the explicit dashboard and Reels navigation shells", () => {
    expect(shouldUseOfflineNavigationFallback(request("GET", "/"))).toBe(true);
    expect(shouldUseOfflineNavigationFallback(request("GET", "/offline"))).toBe(true);
    expect(shouldUseOfflineNavigationFallback(request("GET", "/videos"))).toBe(false);
    expect(shouldUseOfflineNavigationFallback(request("GET", "/unknown"))).toBe(false);
    expect(shouldUseOfflineNavigationFallback(request("POST", "/"))).toBe(false);
  });

  it("excludes API catalog and stream requests from shell caching", () => {
    expect(isExcludedFromShellCaching(request("GET", "http://localhost:8000/videos"))).toBe(true);
    expect(isExcludedFromShellCaching(request("GET", "/videos"))).toBe(true);
    expect(isExcludedFromShellCaching(request("GET", "/videos/video-id"))).toBe(true);
    expect(isExcludedFromShellCaching(request("GET", "/api/videos"))).toBe(true);
    expect(isExcludedFromShellCaching(request("GET", "/api/videos/video-id/stream"))).toBe(true);
    expect(isExcludedFromShellCaching(request("GET", "/videos/video-id/stream"))).toBe(true);
  });

  it("precaches only the canonical dashboard, Reels, and manifest shells", () => {
    expect(isExplicitApplicationShellPath("/")).toBe(true);
    expect(isExplicitApplicationShellPath("/offline")).toBe(true);
    expect(isExplicitApplicationShellPath("/videos")).toBe(false);
    expect(isExplicitApplicationShellPath("/unknown")).toBe(false);
    expect(createApplicationShellPrecacheEntriesFromBuildInputs()).toEqual(expect.arrayContaining([
      expect.objectContaining({ url: HOME_SHELL_URL }),
      expect.objectContaining({ url: OFFLINE_SHELL_URL }),
      expect.objectContaining({ url: WEB_MANIFEST_URL }),
    ]));
    expect(createApplicationShellPrecacheEntriesFromBuildInputs()).not.toEqual(expect.arrayContaining([
      expect.objectContaining({ url: "/videos" }),
    ]));
  });

  it("keeps the current shell and media caches when cleaning obsolete shell caches", () => {
    expect(selectOutdatedShellCaches(
      ["serwist-precache-old-http://localhost:3000/", "serwist-precache-current-http://localhost:3000/", OFFLINE_MEDIA_CACHE_NAME],
      "serwist-precache-current-http://localhost:3000/",
      "http://localhost:3000/",
    )).toEqual(["serwist-precache-old-http://localhost:3000/"]);
  });
});

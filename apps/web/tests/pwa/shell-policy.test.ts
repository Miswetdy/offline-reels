import { describe, expect, it } from "vitest";

import {
  OFFLINE_MEDIA_CACHE_NAME,
  isExplicitApplicationShellPath,
  isExcludedFromShellCaching,
  selectOutdatedShellCaches,
  shouldUseOfflineNavigationFallback,
} from "../../lib/pwa/shell-policy";
import {
  OFFLINE_SHELL_URL,
  VIDEOS_SHELL_URL,
  WEB_MANIFEST_URL,
  createApplicationShellPrecacheEntry,
  createApplicationShellPrecacheEntriesFromBuildInputs,
} from "../../lib/pwa/offline-shell-precache";

const applicationOrigin = "http://localhost:3000";

function request(method: string, pathOrUrl: string) {
  return {
    method,
    url: new URL(pathOrUrl, applicationOrigin),
    applicationOrigin,
  };
}

describe("application-shell cache policy", () => {
  it("uses a revisioned /offline entry for the navigation fallback", () => {
    const first = createApplicationShellPrecacheEntry(OFFLINE_SHELL_URL, "offline shell");
    const same = createApplicationShellPrecacheEntry(OFFLINE_SHELL_URL, "offline shell");
    const changed = createApplicationShellPrecacheEntry(OFFLINE_SHELL_URL, "updated shell");

    expect(first).toEqual({ url: OFFLINE_SHELL_URL, revision: expect.any(String) });
    expect(first.revision).toHaveLength(64);
    expect(same.revision).toBe(first.revision);
    expect(changed.revision).not.toBe(first.revision);
  });

  it("uses the offline fallback only for same-origin GET /offline", () => {
    expect(shouldUseOfflineNavigationFallback(request("GET", "/offline"))).toBe(true);
    expect(shouldUseOfflineNavigationFallback(request("GET", "/videos"))).toBe(false);
    expect(shouldUseOfflineNavigationFallback(request("POST", "/offline"))).toBe(false);
  });

  it("excludes backend, streams, and non-GET requests from shell caching", () => {
    expect(isExcludedFromShellCaching(request("GET", "http://localhost:8000/videos"))).toBe(true);
    expect(isExcludedFromShellCaching(request("GET", "/videos/video-id/stream"))).toBe(true);
    expect(isExcludedFromShellCaching(request("DELETE", "/offline"))).toBe(true);
  });

  it("precaches only explicit offline and videos navigation shells", () => {
    expect(isExplicitApplicationShellPath("/offline")).toBe(true);
    expect(isExplicitApplicationShellPath("/videos")).toBe(true);
    expect(isExplicitApplicationShellPath("/unknown")).toBe(false);
  });

  it("adds the web manifest as a deterministic application-shell precache entry", () => {
    const entries = createApplicationShellPrecacheEntriesFromBuildInputs();

    expect(entries).toEqual(expect.arrayContaining([
      expect.objectContaining({ url: OFFLINE_SHELL_URL }),
      expect.objectContaining({ url: VIDEOS_SHELL_URL }),
      expect.objectContaining({ url: WEB_MANIFEST_URL }),
    ]));
  });

  it("keeps the current shell and media caches when cleaning obsolete shell caches", () => {
    expect(
      selectOutdatedShellCaches(
        [
          "serwist-precache-old-http://localhost:3000/",
          "serwist-precache-current-http://localhost:3000/",
          OFFLINE_MEDIA_CACHE_NAME,
          "another-app-precache-old-http://localhost:3001/",
        ],
        "serwist-precache-current-http://localhost:3000/",
        "http://localhost:3000/",
      ),
    ).toEqual(["serwist-precache-old-http://localhost:3000/"]);
  });
});

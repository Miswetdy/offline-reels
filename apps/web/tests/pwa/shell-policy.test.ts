import { describe, expect, it } from "vitest";

import {
  OFFLINE_MEDIA_CACHE_NAME,
  isExcludedFromShellCaching,
  selectOutdatedShellCaches,
  shouldUseOfflineNavigationFallback,
} from "../../lib/pwa/shell-policy";
import { OFFLINE_SHELL_URL, createOfflineShellPrecacheEntry } from "../../lib/pwa/offline-shell-precache";

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
    const first = createOfflineShellPrecacheEntry("<html>offline shell</html>");
    const same = createOfflineShellPrecacheEntry("<html>offline shell</html>");
    const changed = createOfflineShellPrecacheEntry("<html>updated shell</html>");

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

  it("excludes backend, API, streams, and non-GET requests from shell caching", () => {
    expect(isExcludedFromShellCaching(request("GET", "http://localhost:8000/videos"))).toBe(true);
    expect(isExcludedFromShellCaching(request("GET", "/videos"))).toBe(true);
    expect(isExcludedFromShellCaching(request("GET", "/videos/video-id/stream"))).toBe(true);
    expect(isExcludedFromShellCaching(request("DELETE", "/offline"))).toBe(true);
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

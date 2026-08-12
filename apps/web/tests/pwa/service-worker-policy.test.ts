import { describe, expect, it } from "vitest";

import { OFFLINE_MEDIA_CACHE_NAME, selectOutdatedShellCaches } from "../../lib/pwa/shell-policy";
import {
  serviceWorkerCachingPolicy,
  serviceWorkerLifecyclePolicy,
  serviceWorkerRegistrationOptions,
  serviceWorkerScriptCacheControl,
  isNeverCacheManagementPath,
} from "../../lib/pwa/service-worker-policy";

describe("Service Worker lifecycle policy", () => {
  it("uses one scoped registration without reload-on-online", () => {
    expect(serviceWorkerRegistrationOptions).toEqual({
      swUrl: "/serwist/sw.js",
      scope: "/",
      reloadOnOnline: false,
    });
  });

  it("lets a new worker wait instead of forcing activation", () => {
    expect(serviceWorkerLifecyclePolicy.skipWaiting).toBe(false);
    expect(serviceWorkerLifecyclePolicy.clientsClaim).toBe(true);
  });

  it("does not configure runtime caching for API or media requests", () => {
    expect(serviceWorkerCachingPolicy.runtimeCaching).toEqual([]);
  });

  it("never permits an intermediary to retain a stale worker script", () => {
    expect(serviceWorkerScriptCacheControl).toBe("no-store, max-age=0, must-revalidate");
  });

  it("keeps management, pairing, login capabilities, and CSRF-bearing routes out of every cache", () => {
    expect(isNeverCacheManagementPath("/api/management/pairing/exchange")).toBe(true);
    expect(isNeverCacheManagementPath("/api/management/session")).toBe(true);
    expect(isNeverCacheManagementPath("/api/instagram/login-sessions/any-id")).toBe(true);
    expect(isNeverCacheManagementPath("/api/instagram/collection-runs/any-id")).toBe(true);
    expect(isNeverCacheManagementPath("/connect/any-id")).toBe(true);
    expect(isNeverCacheManagementPath("/api/videos")).toBe(false);
  });

  it("never selects the offline media cache for shell cleanup", () => {
    expect(
      selectOutdatedShellCaches(
        ["offline-reels-shell-precache-old-http://localhost:3000/", OFFLINE_MEDIA_CACHE_NAME],
        "offline-reels-shell-precache-current-http://localhost:3000/",
        "http://localhost:3000/",
      ),
    ).toEqual(["offline-reels-shell-precache-old-http://localhost:3000/"]);
  });
});

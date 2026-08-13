export const serviceWorkerLifecyclePolicy = {
  cacheId: "offline-reels-shell",
  skipWaiting: false,
  clientsClaim: true,
} as const;

export const serviceWorkerCachingPolicy = {
  runtimeCaching: [] as never[],
};

/**
 * A regression guard for future runtime routes. Management responses can carry
 * session-derived state and one-time login capabilities, so neither their
 * bodies nor related request metadata may ever enter Serwist or Cache Storage.
 */
export function isNeverCacheManagementPath(pathname: string): boolean {
  return pathname === "/api/management/session"
    || pathname.startsWith("/api/reserve/")
    || pathname.startsWith("/api/management/")
    || pathname === "/api/instagram/status"
    || pathname.startsWith("/api/instagram/login-sessions")
    || pathname.startsWith("/api/instagram/collection-runs")
    || pathname === "/api/instagram/normalization-status"
    || pathname === "/api/instagram/collection-settings"
    || pathname.startsWith("/connect/");
}

export const serviceWorkerRegistrationOptions = {
  swUrl: "/serwist/sw.js",
  scope: "/",
  reloadOnOnline: false,
} as const;

// The worker is the app's update manifest. It must never sit behind a
// browser or intermediary cache after a deployment, especially on iOS PWA.
export const serviceWorkerScriptCacheControl = "no-store, max-age=0, must-revalidate";

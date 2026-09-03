export const HOME_SHELL_PATH = "/";
export const OFFLINE_SHELL_PATH = "/offline";
export const OFFLINE_MEDIA_CACHE_NAME = "offline-reels-media-v1";
const SERWIST_PRECACHE_MARKER = "-precache-";

export const offlineNavigationAllowlist = [/^\/$/, /^\/offline$/];

export type ShellRequest = {
  method: string;
  url: URL;
  applicationOrigin: string;
};

export function shouldUseOfflineNavigationFallback(request: ShellRequest): boolean {
  return (
    request.method === "GET" &&
    request.url.origin === request.applicationOrigin &&
    offlineNavigationAllowlist.some((pattern) => pattern.test(request.url.pathname))
  );
}

export function isExcludedFromShellCaching(request: ShellRequest): boolean {
  if (request.method !== "GET" || request.url.origin !== request.applicationOrigin) {
    return true;
  }

  return /^\/api\/videos(?:\/[^/]+\/stream)?$/.test(request.url.pathname)
    || /^\/videos(?:\/.*)?$/.test(request.url.pathname);
}

export function isExplicitApplicationShellPath(pathname: string): boolean {
  return pathname === HOME_SHELL_PATH || pathname === OFFLINE_SHELL_PATH;
}

export function selectOutdatedShellCaches(
  cacheNames: string[],
  currentShellCache: string,
  serviceWorkerScope: string,
): string[] {
  return cacheNames.filter(
    (cacheName) =>
      cacheName !== currentShellCache &&
      cacheName.includes(SERWIST_PRECACHE_MARKER) &&
      cacheName.includes(serviceWorkerScope),
  );
}

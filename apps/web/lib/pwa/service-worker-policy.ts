export const serviceWorkerLifecyclePolicy = {
  cacheId: "offline-reels-shell",
  skipWaiting: false,
  clientsClaim: true,
} as const;

export const serviceWorkerCachingPolicy = {
  runtimeCaching: [] as never[],
};

export const serviceWorkerRegistrationOptions = {
  swUrl: "/serwist/sw.js",
  scope: "/",
  reloadOnOnline: false,
} as const;

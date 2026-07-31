import type { PrecacheEntry, SerwistGlobalConfig } from "serwist";
import { Route, Serwist } from "serwist";

import { offlineNavigationAllowlist } from "../lib/pwa/shell-policy";
import { handleOfflineMediaRequest, shouldHandleOfflineMediaRequest } from "../lib/pwa/offline-media-route";
import { serviceWorkerCachingPolicy, serviceWorkerLifecyclePolicy } from "../lib/pwa/service-worker-policy";

declare global {
  interface WorkerGlobalScope extends SerwistGlobalConfig {
    __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
  }
}

const injectedManifest = (self as unknown as WorkerGlobalScope).__SW_MANIFEST;

if (injectedManifest === undefined) {
  throw new Error("Serwist did not inject the production precache manifest.");
}

const serwist = new Serwist({
  cacheId: serviceWorkerLifecyclePolicy.cacheId,
  precacheEntries: injectedManifest,
  precacheOptions: {
    navigateFallback: "/offline",
    navigateFallbackAllowlist: offlineNavigationAllowlist,
  },
  skipWaiting: serviceWorkerLifecyclePolicy.skipWaiting,
  clientsClaim: serviceWorkerLifecyclePolicy.clientsClaim,
  runtimeCaching: serviceWorkerCachingPolicy.runtimeCaching,
  disableDevLogs: true,
});

serwist.registerRoute(new Route(shouldHandleOfflineMediaRequest, ({ request }) => handleOfflineMediaRequest(request)));
serwist.addEventListeners();

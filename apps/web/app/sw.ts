import type { PrecacheEntry, SerwistGlobalConfig } from "serwist";
import { Serwist } from "serwist";

import { offlineNavigationAllowlist } from "../lib/pwa/shell-policy";

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
  cacheId: "offline-reels-shell",
  precacheEntries: injectedManifest,
  precacheOptions: {
    navigateFallback: "/offline",
    navigateFallbackAllowlist: offlineNavigationAllowlist,
  },
  skipWaiting: true,
  clientsClaim: true,
  disableDevLogs: true,
});

serwist.addEventListeners();

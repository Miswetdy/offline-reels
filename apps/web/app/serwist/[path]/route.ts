import { createSerwistRoute } from "@serwist/turbopack";

import { createOfflineShellPrecacheEntryFromBuildInputs } from "../../../lib/pwa/offline-shell-precache";

export const serwistRouteOptions = {
  swSrc: "app/sw.ts",
  useNativeEsbuild: true,
  additionalPrecacheEntries: [createOfflineShellPrecacheEntryFromBuildInputs()],
};

export const { dynamic, dynamicParams, revalidate, generateStaticParams, GET } = createSerwistRoute(serwistRouteOptions);

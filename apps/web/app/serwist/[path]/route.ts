import { createSerwistRoute } from "@serwist/turbopack";

import { createApplicationShellPrecacheEntriesFromBuildInputs } from "../../../lib/pwa/offline-shell-precache";

export const serwistRouteOptions = {
  swSrc: "app/sw.ts",
  useNativeEsbuild: true,
  additionalPrecacheEntries: createApplicationShellPrecacheEntriesFromBuildInputs(),
};

export const { dynamic, dynamicParams, revalidate, generateStaticParams, GET } = createSerwistRoute(serwistRouteOptions);

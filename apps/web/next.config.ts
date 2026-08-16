import type { NextConfig } from "next";
import { withSerwist } from "@serwist/turbopack";

import { serviceWorkerScriptCacheControl } from "./lib/pwa/service-worker-policy";

// These values are emitted by Next while building. Browser code reads only
// these literals, never a public runtime environment/URL/storage switch.
const stage9FixtureBuild = process.env.NEXT_PUBLIC_STAGE9_FIXTURE_MODE === "true";
const autoRefillFixtureBuild = process.env.NEXT_PUBLIC_OFFLINE_REELS_AUTO_REFILL_FIXTURE === "true";

const nextConfig: NextConfig = {
  output: "standalone",
  env: {
    OFFLINE_REELS_BUILD_STAGE9_FIXTURE: stage9FixtureBuild ? "true" : "false",
    OFFLINE_REELS_BUILD_AUTO_REFILL: autoRefillFixtureBuild ? "true" : "false",
  },
  async headers() {
    return [{
      source: "/serwist/sw.js",
      headers: [{ key: "Cache-Control", value: serviceWorkerScriptCacheControl }],
    }];
  },
};

export default withSerwist(nextConfig);

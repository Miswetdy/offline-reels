import type { NextConfig } from "next";
import { withSerwist } from "@serwist/turbopack";

import { serviceWorkerScriptCacheControl } from "./lib/pwa/service-worker-policy";

const nextConfig: NextConfig = {
  output: "standalone",
  async headers() {
    return [{
      source: "/serwist/sw.js",
      headers: [{ key: "Cache-Control", value: serviceWorkerScriptCacheControl }],
    }];
  },
};

export default withSerwist(nextConfig);

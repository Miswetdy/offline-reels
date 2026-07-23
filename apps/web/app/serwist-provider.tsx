"use client";

import { SerwistProvider } from "@serwist/turbopack/react";
import type { ReactNode } from "react";

import { serviceWorkerRegistrationOptions } from "../lib/pwa/service-worker-policy";

export function OfflineShellProvider({ children }: { children: ReactNode }) {
  return (
    <SerwistProvider
      swUrl={serviceWorkerRegistrationOptions.swUrl}
      disable={process.env.NODE_ENV !== "production"}
      reloadOnOnline={serviceWorkerRegistrationOptions.reloadOnOnline}
      options={{ scope: serviceWorkerRegistrationOptions.scope }}
    >
      {children}
    </SerwistProvider>
  );
}

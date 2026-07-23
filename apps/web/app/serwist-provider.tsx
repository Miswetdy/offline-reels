"use client";

import { SerwistProvider } from "@serwist/turbopack/react";
import type { ReactNode } from "react";

export function OfflineShellProvider({ children }: { children: ReactNode }) {
  return (
    <SerwistProvider
      swUrl="/serwist/sw.js"
      disable={process.env.NODE_ENV !== "production"}
      reloadOnOnline={false}
      options={{ scope: "/" }}
    >
      {children}
    </SerwistProvider>
  );
}

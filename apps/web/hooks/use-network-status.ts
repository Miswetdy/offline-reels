"use client";

import { useEffect, useState } from "react";

export function getInitialNetworkStatus(): boolean {
  return typeof navigator === "undefined" ? true : navigator.onLine;
}

export function useNetworkStatus(): boolean {
  const [isOnline, setIsOnline] = useState(getInitialNetworkStatus);

  useEffect(() => {
    const updateNetworkStatus = () => setIsOnline(navigator.onLine);

    updateNetworkStatus();
    window.addEventListener("online", updateNetworkStatus);
    window.addEventListener("offline", updateNetworkStatus);
    return () => {
      window.removeEventListener("online", updateNetworkStatus);
      window.removeEventListener("offline", updateNetworkStatus);
    };
  }, []);

  return isOnline;
}

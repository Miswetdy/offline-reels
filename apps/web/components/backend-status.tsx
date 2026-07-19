"use client";

import { useEffect, useState } from "react";

import { checkBackendLive, type BackendAvailability } from "../lib/api/health";

export function BackendStatus() {
  const [availability, setAvailability] = useState<BackendAvailability>("checking");

  useEffect(() => {
    let active = true;

    checkBackendLive().then((nextAvailability) => {
      if (active) {
        setAvailability(nextAvailability);
      }
    });

    return () => {
      active = false;
    };
  }, []);

  const message = {
    checking: "Checking Backend API…",
    available: "Backend API is available.",
    unavailable: "Backend API is unavailable.",
  }[availability];

  const color = availability === "available" ? "text-emerald-700" : availability === "unavailable" ? "text-red-700" : "text-amber-700";

  return (
    <p aria-live="polite" className={`mt-6 font-medium ${color}`}>
      {message}
    </p>
  );
}

"use client";

import { useSerwist } from "@serwist/turbopack/react";
import type { SerwistLifecycleWaitingEvent } from "@serwist/window";
import { useEffect, useRef, useState } from "react";

type PwaUpdateNotificationProps = {
  onReload?: () => void;
};

function reloadPage() {
  window.location.reload();
}

export function PwaUpdateNotification({ onReload = reloadPage }: PwaUpdateNotificationProps) {
  const { serwist } = useSerwist();
  const [hasWaitingWorker, setHasWaitingWorker] = useState(false);
  const [activationRequested, setActivationRequested] = useState(false);
  const activationRequestedRef = useRef(false);
  const waitingWorkerRef = useRef<ServiceWorker | undefined>(undefined);
  const activationRequestedWorkerRef = useRef<ServiceWorker | undefined>(undefined);
  const reloadedRef = useRef(false);

  useEffect(() => {
    if (serwist === null) return;

    const handleWaiting = (event: SerwistLifecycleWaitingEvent) => {
      waitingWorkerRef.current = event.sw;
      if (activationRequestedWorkerRef.current !== event.sw) {
        activationRequestedRef.current = false;
        setActivationRequested(false);
      }
      setHasWaitingWorker(true);
    };
    const handleControlling = () => {
      if (!activationRequestedRef.current || reloadedRef.current) return;
      reloadedRef.current = true;
      onReload();
    };

    serwist.addEventListener("waiting", handleWaiting);
    serwist.addEventListener("controlling", handleControlling);
    return () => {
      serwist.removeEventListener("waiting", handleWaiting);
      serwist.removeEventListener("controlling", handleControlling);
    };
  }, [onReload, serwist]);

  const activateUpdate = () => {
    if (serwist === null || !hasWaitingWorker || activationRequestedRef.current) return;
    activationRequestedRef.current = true;
    activationRequestedWorkerRef.current = waitingWorkerRef.current;
    setActivationRequested(true);
    serwist.messageSkipWaiting();
  };

  if (!hasWaitingWorker) return null;

  return (
    <aside
      className="fixed left-4 top-[calc(env(safe-area-inset-top)+1rem)] z-30 flex max-w-[calc(100%-7rem)] items-center gap-3 rounded-full bg-slate-900/95 px-3 py-2 text-sm text-white shadow-lg"
      role="status"
      aria-live="polite"
    >
      <span className="min-w-0">Доступна новая версия</span>
      <button
        className="shrink-0 rounded-full bg-white px-3 py-1 font-medium text-slate-900 disabled:cursor-wait disabled:opacity-70"
        type="button"
        disabled={activationRequested}
        onClick={activateUpdate}
      >
        Обновить
      </button>
    </aside>
  );
}

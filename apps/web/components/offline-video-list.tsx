"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppBottomNavigation } from "./app-bottom-navigation";
import { VerticalVideoFeed, type VerticalVideoFeedItem } from "./vertical-video-feed";
import { OfflineStorageError, toOfflineStorageError } from "../lib/offline/errors";
import { getMediaCacheKey } from "../lib/offline/media-cache";
import { reconcileOfflineLibrary } from "../lib/offline/reconciliation";
import { listCompletedOfflineVideos } from "../lib/offline/repository";
import type { OfflineVideoRecord } from "../lib/offline/types";

type OfflineLibraryState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; records: OfflineVideoRecord[] };

type ServiceWorkerReadiness = "controlled" | "waiting" | "unavailable";

function getServiceWorkerReadiness(): ServiceWorkerReadiness {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return "unavailable";
  return navigator.serviceWorker.controller === null ? "waiting" : "controlled";
}

function sortOfflineRecords(records: OfflineVideoRecord[]): OfflineVideoRecord[] {
  return [...records].sort((left, right) =>
    (right.downloadedAt ?? "").localeCompare(left.downloadedAt ?? "")
    || right.createdAt.localeCompare(left.createdAt)
    || right.id.localeCompare(left.id),
  );
}

export function OfflineVideoList() {
  const [reloadAttempt, setReloadAttempt] = useState(0);
  const [state, setState] = useState<OfflineLibraryState>({ status: "loading" });
  const [serviceWorkerReadiness, setServiceWorkerReadiness] = useState<ServiceWorkerReadiness>(getServiceWorkerReadiness);
  const refreshServiceWorkerControl = useCallback(() => {
    setServiceWorkerReadiness(getServiceWorkerReadiness());
  }, []);

  useEffect(() => {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
    const registration = navigator.serviceWorker;
    registration.addEventListener("controllerchange", refreshServiceWorkerControl);
    void registration.ready.then(refreshServiceWorkerControl, refreshServiceWorkerControl);
    return () => registration.removeEventListener("controllerchange", refreshServiceWorkerControl);
  }, [refreshServiceWorkerControl]);

  useEffect(() => {
    let disposed = false;
    void (async () => {
      try {
        const reconciliation = await reconcileOfflineLibrary();
        if (reconciliation.storageUnavailable) throw new OfflineStorageError("browser_storage_unavailable");
        const records = await listCompletedOfflineVideos();
        if (!disposed) setState({ status: "success", records: sortOfflineRecords(records) });
      } catch (error) {
        if (!disposed) setState({ status: "error", message: toOfflineStorageError(error).userMessage });
      }
    })();
    return () => {
      disposed = true;
    };
  }, [reloadAttempt]);

  const refresh = useCallback(() => {
    setState({ status: "loading" });
    setReloadAttempt((value) => value + 1);
  }, []);

  const feedItems = useMemo<VerticalVideoFeedItem[]>(() => {
    if (state.status !== "success") return [];
    return state.records.map((record) => ({
      id: record.id,
      title: record.title,
      mediaUrl: getMediaCacheKey(record.id),
    }));
  }, [state]);

  if (state.status === "loading") {
    return <main className="grid h-dvh place-items-center" aria-live="polite">Загрузка офлайн-библиотеки…</main>;
  }
  if (state.status === "error") {
    return (
      <main className="grid h-dvh place-items-center gap-4 p-6 text-center">
        <p role="alert">{state.message}</p>
        <button className="rounded bg-slate-900 px-4 py-2 text-white" type="button" onClick={refresh}>Повторить</button>
        <Link className="text-slate-700 underline" href="/">Перейти на главную</Link>
      </main>
    );
  }

  if (state.records.length === 0) {
    return (
      <main className="grid h-dvh place-items-center gap-4 p-6 text-center">
        <p>Пока нет скачанных Reels</p>
        <Link className="rounded bg-slate-900 px-4 py-2 text-white" href="/">Перейти на главную</Link>
        <AppBottomNavigation activeRoute="offline" />
      </main>
    );
  }

  if (serviceWorkerReadiness === "unavailable") {
    return (
      <main className="grid h-dvh place-items-center gap-4 p-6 text-center">
        <p role="alert">Этот браузер не поддерживает Service Worker для офлайн-воспроизведения.</p>
        <Link className="text-slate-700 underline" href="/">Перейти на главную</Link>
      </main>
    );
  }

  if (serviceWorkerReadiness !== "controlled") {
    return (
      <main className="grid h-dvh place-items-center gap-4 p-6 text-center">
        <p role="alert">Офлайн-воспроизведение станет доступно после активации Service Worker.</p>
        <button className="rounded bg-slate-900 px-4 py-2 text-white" type="button" onClick={refreshServiceWorkerControl}>Проверить повторно</button>
        <Link className="text-slate-700 underline" href="/">Перейти на главную</Link>
      </main>
    );
  }

  return (
    <>
      <VerticalVideoFeed items={feedItems} controlsMode="reels" hasBottomNavigation showMetadata={false} />
      <AppBottomNavigation activeRoute="offline" withReelsGlassBackdrop />
    </>
  );
}

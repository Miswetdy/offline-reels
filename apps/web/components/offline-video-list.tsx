"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AppBottomNavigation } from "./app-bottom-navigation";
import { VerticalVideoFeed, type VerticalVideoFeedItem } from "./vertical-video-feed";
import { OfflineStorageError, toOfflineStorageError } from "../lib/offline/errors";
import { getMediaCacheKey } from "../lib/offline/media-cache";
import { reconcileOfflineLibrary } from "../lib/offline/reconciliation";
import { listCompletedOfflineVideos } from "../lib/offline/repository";
import type { OfflineVideoRecord } from "../lib/offline/types";

// Keep fixture-only controls out of the production client bundle. This is a
// build-time literal supplied only by Next's build configuration; there is no
// URL, localStorage, or public runtime switch.
const STAGE9_FIXTURE_BUILD = process.env.OFFLINE_REELS_BUILD_STAGE9_FIXTURE === "true";

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
  const mountedRef = useRef(false);
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

  useEffect(() => {
    // Keep the ordinary offline-shell unit surface free from the lifecycle
    // graph; real PWA browsers always expose IndexedDB.
    if (typeof indexedDB === "undefined") return;
    mountedRef.current = true;
    let disposed = false;
    let lifecycle: import("../lib/offline/view-lifecycle").ViewedReelLifecycle | undefined;
    let unsubscribe: (() => void) | undefined;
    const refreshLibrary = () => setReloadAttempt((value) => value + 1);
    const run = () => {
      void import("../lib/offline/view-lifecycle").then(({ getViewedReelLifecycle }) => {
        if (disposed) return undefined;
        lifecycle = getViewedReelLifecycle();
        unsubscribe ??= lifecycle.subscribe(refreshLibrary);
        return lifecycle.reconcile();
      }).then(() => { if (!disposed) refreshLibrary(); }, () => undefined);
    };
    const visible = () => { if (document.visibilityState === "visible") run(); };
    window.addEventListener("online", run);
    window.addEventListener("pageshow", run);
    document.addEventListener("visibilitychange", visible);
    run();
    return () => {
      disposed = true;
      mountedRef.current = false;
      // The expired active Reel may be deleted immediately after this route
      // unmounts. Keeping its ID would incorrectly retain it forever.
      lifecycle?.setActiveVideoId(null);
      unsubscribe?.();
      window.removeEventListener("online", run); window.removeEventListener("pageshow", run); document.removeEventListener("visibilitychange", visible);
    };
  }, []);

  const refresh = useCallback(() => {
    setState({ status: "loading" });
    setReloadAttempt((value) => value + 1);
  }, []);
  const advanceFixtureClock = useCallback(() => {
    if (!STAGE9_FIXTURE_BUILD) return;
    void import("../lib/offline/fixture-clock").then(({ advanceStage9FixtureClockOneHour }) => {
      if (!advanceStage9FixtureClockOneHour()) return undefined;
      return import("../lib/offline/view-lifecycle").then(({ getViewedReelLifecycle }) => getViewedReelLifecycle().reconcile());
    })
      .then(() => setReloadAttempt((value) => value + 1), () => undefined);
  }, []);
  const recordViewed = useCallback((videoId: string) => {
    void import("../lib/offline/view-lifecycle").then(({ getViewedReelLifecycle }) => getViewedReelLifecycle().recordViewed(videoId)).then(() => {
      setState((current) => current.status !== "success" ? current : {
        status: "success",
        records: current.records.map((record) => record.id === videoId ? {
          ...record,
          viewedAt: record.viewedAt ?? new Date().toISOString(),
          deletionState: "pending",
        } : record),
      });
    });
  }, []);

  const feedItems = useMemo<VerticalVideoFeedItem[]>(() => {
    if (state.status !== "success") return [];
    return state.records.map((record) => ({
      id: record.id,
      title: record.title,
      mediaUrl: getMediaCacheKey(record.id),
    }));
  }, [state]);
  const availableReserveCount = state.status === "success"
    ? state.records.filter((record) => !record.viewedAt).length
    : 0;

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
        <p role="status" aria-live="polite" aria-label="Локальный запас">Запас: {availableReserveCount}</p>
        {STAGE9_FIXTURE_BUILD ? <button className="min-h-11 rounded-xl border border-slate-300 px-4 py-2 font-medium" type="button" onClick={advanceFixtureClock}>Fixture: проверить удаление</button> : null}
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
      <div className="pointer-events-none fixed left-3 top-[calc(env(safe-area-inset-top)+0.75rem)] z-30 max-w-[calc(100vw-1.5rem)] rounded-full bg-black/65 px-3 py-1.5 text-sm font-medium text-white shadow-sm" role="status" aria-live="polite" aria-label="Локальный запас">
        <span>Запас: {availableReserveCount}</span>
      </div>
      {STAGE9_FIXTURE_BUILD ? <button className="fixed right-3 top-[calc(env(safe-area-inset-top)+0.75rem)] z-30 min-h-11 rounded-full bg-white/90 px-3 text-sm font-medium text-slate-950 shadow-sm" type="button" onClick={advanceFixtureClock}>Fixture: проверить удаление</button> : null}
      <VerticalVideoFeed
        items={feedItems}
        controlsMode="reels"
        hasBottomNavigation
        showMetadata={false}
        renderActions={(item) => {
          const record = state.status === "success" ? state.records.find((candidate) => candidate.id === item.id) : undefined;
          if (!record?.viewedAt) return null;
          if (record.deletionState !== "deleting" && record.deletionState !== "failed") return null;
          if (record.deletionState === "deleting") return <p role="status">Освобождаем место</p>;
          if (record.deletionState === "failed") return <p role="status">Не удалось освободить место — повторим позже</p>;
        }}
        onActiveItemChange={(item) => {
          void import("../lib/offline/view-lifecycle").then(({ getViewedReelLifecycle }) =>
            // A dynamic import can resolve after route unmount. It must not
            // resurrect an expired active ID after cleanup has released it.
            mountedRef.current ? getViewedReelLifecycle().setActiveVideoId(item?.id ?? null) : undefined,
          );
        }}
        onUserSwipeCommitted={(previous) => recordViewed(previous.id)}
      />
      <AppBottomNavigation activeRoute="offline" withReelsGlassBackdrop />
    </>
  );
}

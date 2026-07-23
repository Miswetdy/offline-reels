"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { NetworkStatusIndicator } from "./network-status-indicator";
import { VerticalVideoFeed, type VerticalVideoFeedItem } from "./vertical-video-feed";
import { OfflineStorageError, toOfflineStorageError } from "../lib/offline/errors";
import { getMediaCacheKey } from "../lib/offline/media-cache";
import { clearOfflineLibrary, deleteOfflineLibraryVideo } from "../lib/offline/library-management";
import { reconcileOfflineLibrary } from "../lib/offline/reconciliation";
import { listCompletedOfflineVideos } from "../lib/offline/repository";
import { getStorageEstimate, type LocalStorageEstimate } from "../lib/offline/storage";
import type { OfflineVideoRecord } from "../lib/offline/types";

type OfflineLibraryState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; records: OfflineVideoRecord[]; estimate: LocalStorageEstimate };

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

function formatBytes(byteSize: number): string {
  return `${byteSize.toLocaleString()} Б`;
}

export function OfflineVideoList() {
  const [reloadAttempt, setReloadAttempt] = useState(0);
  const [state, setState] = useState<OfflineLibraryState>({ status: "loading" });
  const [pendingVideoId, setPendingVideoId] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
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
        if (reconciliation.storageUnavailable) {
          throw new OfflineStorageError("browser_storage_unavailable");
        }
        const [records, estimate] = await Promise.all([listCompletedOfflineVideos(), getStorageEstimate()]);
        if (!disposed) setState({ status: "success", records: sortOfflineRecords(records), estimate });
      } catch (error) {
        if (!disposed) setState({ status: "error", message: toOfflineStorageError(error).userMessage });
      }
    })();
    return () => {
      disposed = true;
    };
  }, [reloadAttempt]);

  const refresh = useCallback((background = false) => {
    if (!background) setState({ status: "loading" });
    setReloadAttempt((value) => value + 1);
  }, []);

  const deleteVideo = useCallback(async (videoId: string) => {
    setPendingVideoId(videoId);
    setFeedback(null);
    try {
      await deleteOfflineLibraryVideo(videoId);
      refresh(true);
    } catch (error) {
      setFeedback(toOfflineStorageError(error).userMessage);
      refresh(true);
    } finally {
      setPendingVideoId(null);
    }
  }, [refresh]);

  const clearLibrary = useCallback(async () => {
    if (!window.confirm("Очистить офлайн-библиотеку?")) return;
    setClearing(true);
    setFeedback(null);
    try {
      await clearOfflineLibrary();
      refresh(true);
    } catch (error) {
      setFeedback(toOfflineStorageError(error).userMessage);
      refresh(true);
    } finally {
      setClearing(false);
    }
  }, [refresh]);

  const feedItems = useMemo<VerticalVideoFeedItem[]>(() => {
    if (state.status !== "success") return [];
    return state.records.map((record) => ({
      id: record.id,
      title: record.title,
      mediaUrl: getMediaCacheKey(record.id),
      subtitle: formatBytes(record.byteSize),
    }));
  }, [state]);

  if (state.status === "loading") {
    return <main className="grid h-dvh place-items-center" aria-live="polite">Загрузка офлайн-библиотеки…</main>;
  }
  if (state.status === "error") {
    return (
      <main className="grid h-dvh place-items-center gap-4 p-6 text-center">
        <p role="alert">{state.message}</p>
        <button className="rounded bg-slate-900 px-4 py-2 text-white" type="button" onClick={() => refresh()}>
          Повторить
        </button>
        <Link className="text-slate-700 underline" href="/videos">К онлайн-ленте</Link>
      </main>
    );
  }

  const librarySize = state.records.reduce((total, record) => total + record.byteSize, 0);
  if (state.records.length === 0) {
    return (
      <main className="grid h-dvh place-items-center gap-4 p-6 text-center">
        <p>Офлайн-библиотека пуста</p>
        <Link className="rounded bg-slate-900 px-4 py-2 text-white" href="/videos">Перейти к видео</Link>
      </main>
    );
  }

  if (serviceWorkerReadiness === "unavailable") {
    return (
      <main className="grid h-dvh place-items-center gap-4 p-6 text-center">
        <p role="alert">Этот браузер не поддерживает Service Worker для офлайн-воспроизведения.</p>
        <Link className="text-slate-700 underline" href="/videos">К онлайн-ленте</Link>
      </main>
    );
  }

  if (serviceWorkerReadiness !== "controlled") {
    return (
      <main className="grid h-dvh place-items-center gap-4 p-6 text-center">
        <p role="alert">Офлайн-воспроизведение станет доступно после активации Service Worker.</p>
        <button className="rounded bg-slate-900 px-4 py-2 text-white" type="button" onClick={refreshServiceWorkerControl}>
          Проверить повторно
        </button>
        <Link className="text-slate-700 underline" href="/videos">К онлайн-ленте</Link>
      </main>
    );
  }

  return (
    <>
      <VerticalVideoFeed
        items={feedItems}
        renderActions={(item) => (
          <button
            className="rounded bg-amber-200 px-3 py-1 text-sm text-slate-950 disabled:opacity-50"
            type="button"
            disabled={pendingVideoId !== null || clearing}
            onClick={() => void deleteVideo(item.id)}
          >
            {pendingVideoId === item.id ? "Удаление…" : "Удалить с устройства"}
          </button>
        )}
      />
      <aside className="fixed left-4 top-4 z-20 max-w-[calc(100%-8rem)] rounded bg-black/75 p-3 text-sm text-white" aria-label="Offline library summary">
        <p>Офлайн: {state.records.length} видео · {formatBytes(librarySize)}</p>
        <NetworkStatusIndicator offlineMessage="Офлайн · локальная библиотека доступна" onlineMessage="Онлайн · локальная библиотека" />
        {state.estimate.isAvailable ? (
          <p className="mt-1">Хранилище браузера (примерно): {state.estimate.usage === null ? "недоступно" : formatBytes(state.estimate.usage)}{state.estimate.quota === null ? "" : ` / ${formatBytes(state.estimate.quota)}`}</p>
        ) : <p className="mt-1">Хранилище браузера (примерно): недоступно</p>}
        {feedback ? <p className="mt-1 text-amber-200" role="alert">{feedback}</p> : null}
        <button className="mt-2 rounded bg-amber-200 px-2 py-1 text-slate-950 disabled:opacity-50" type="button" disabled={clearing || pendingVideoId !== null} onClick={() => void clearLibrary()}>
          {clearing ? "Очистка…" : "Очистить офлайн-библиотеку"}
        </button>
        <Link className="mt-2 inline-block underline" href="/videos">К онлайн-ленте</Link>
      </aside>
    </>
  );
}

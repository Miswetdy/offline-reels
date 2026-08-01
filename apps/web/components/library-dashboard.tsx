"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AppBottomNavigation } from "./app-bottom-navigation";
import { useNetworkStatus } from "../hooks/use-network-status";
import { useOfflineDownloads } from "../hooks/use-offline-downloads";
import { getEntireVideoCatalog, type Video } from "../lib/api/videos";
import { hasEstimatedSpaceForDownload, getStorageEstimate, type LocalStorageEstimate } from "../lib/offline/storage";

type CatalogState =
  | { status: "idle"; videos: Video[] }
  | { status: "loading"; videos: Video[] }
  | { status: "error"; videos: Video[] }
  | { status: "success"; videos: Video[] };

export type StorageUsagePresentation = {
  label: string;
  percent: number | null;
};

const UNAVAILABLE_ESTIMATE: LocalStorageEstimate = {
  usage: null,
  quota: null,
  available: null,
  isAvailable: false,
};

export function getStorageUsagePresentation(estimate: LocalStorageEstimate): StorageUsagePresentation {
  if (!estimate.isAvailable || estimate.usage === null || estimate.quota === null || estimate.quota <= 0) {
    return { label: "Не удалось определить заполненность хранилища", percent: null };
  }
  if (estimate.usage <= 0) return { label: "Хранилище не используется — 0%", percent: 0 };

  const percent = Math.min(100, Math.max(0, (estimate.usage / estimate.quota) * 100));
  if (percent < 1) return { label: "Хранилище заполнено менее чем на 1%", percent };
  return { label: `Хранилище заполнено на ${Math.round(percent)}%`, percent };
}

function progressPercent(downloadedBytes: number, totalBytes: number): number {
  if (totalBytes <= 0) return 0;
  return Math.min(100, Math.max(0, Math.round((downloadedBytes / totalBytes) * 100)));
}

export function LibraryDashboard() {
  const isNetworkOnline = useNetworkStatus();
  const {
    snapshot,
    enqueueCatalogAndStart,
    cancelAndClear,
    cancelBatch,
  } = useOfflineDownloads();
  const [catalog, setCatalog] = useState<CatalogState>({ status: "idle", videos: [] });
  const [estimate, setEstimate] = useState<LocalStorageEstimate>(UNAVAILABLE_ESTIMATE);
  const [clearing, setClearing] = useState(false);
  const [actionError, setActionError] = useState<"start" | "clear" | null>(null);
  const [actionPending, setActionPending] = useState<"start" | "clear" | null>(null);
  const catalogAbortRef = useRef<AbortController | null>(null);
  const catalogRequestRef = useRef(0);
  const networkOnlineRef = useRef(isNetworkOnline);

  const refreshEstimate = useCallback(() => {
    void getStorageEstimate().then(setEstimate);
  }, []);

  const invalidateCatalogRequest = useCallback(() => {
    catalogRequestRef.current += 1;
    catalogAbortRef.current?.abort();
    catalogAbortRef.current = null;
  }, []);

  const setOfflineCatalogState = useCallback(() => {
    invalidateCatalogRequest();
    setCatalog((current) => current.status === "idle"
      ? current
      : { status: "idle", videos: current.videos });
  }, [invalidateCatalogRequest]);

  const loadCatalog = useCallback(() => {
    if (!networkOnlineRef.current) {
      setOfflineCatalogState();
      return;
    }

    invalidateCatalogRequest();
    const controller = new AbortController();
    const request = catalogRequestRef.current + 1;
    catalogRequestRef.current = request;
    catalogAbortRef.current = controller;
    setCatalog((current) => ({ status: "loading", videos: current.videos }));
    void getEntireVideoCatalog({ signal: controller.signal }).then(
      (videos) => {
        if (catalogRequestRef.current === request && !controller.signal.aborted && networkOnlineRef.current) {
          setCatalog({ status: "success", videos });
        }
      },
      () => {
        if (catalogRequestRef.current === request && !controller.signal.aborted && networkOnlineRef.current) {
          setCatalog((current) => ({ status: "error", videos: current.videos }));
        }
      },
    );
  }, [invalidateCatalogRequest, setOfflineCatalogState]);

  useEffect(() => {
    networkOnlineRef.current = isNetworkOnline;
  }, [isNetworkOnline]);

  useEffect(() => {
    refreshEstimate();
    if (!isNetworkOnline) {
      let disposed = false;
      invalidateCatalogRequest();
      void Promise.resolve().then(() => {
        if (!disposed) setOfflineCatalogState();
      });
      return () => {
        disposed = true;
        invalidateCatalogRequest();
      };
    }
    loadCatalog();
    return invalidateCatalogRequest;
  }, [invalidateCatalogRequest, isNetworkOnline, loadCatalog, refreshEstimate, setOfflineCatalogState]);

  useEffect(() => {
    refreshEstimate();
  }, [refreshEstimate, snapshot?.completedCount, snapshot?.batchProgress?.state, clearing]);

  const recordsById = useMemo(
    () => new Map((snapshot?.records ?? []).map((record) => [record.id, record])),
    [snapshot?.records],
  );
  const eligibleVideos = useMemo(
    () => catalog.videos.filter((video) => {
      const record = recordsById.get(video.id);
      return record?.status !== "completed" && record?.status !== "queued" && record?.status !== "downloading";
    }),
    [catalog.videos, recordsById],
  );
  const isOnline = isNetworkOnline && (snapshot?.online ?? true);
  const hasActiveDownload = snapshot?.activeVideoId !== null || snapshot?.queuedCount !== 0 || snapshot?.clearing === true;
  const nextCandidate = eligibleVideos[0];
  const enoughSpace = nextCandidate === undefined || hasEstimatedSpaceForDownload(nextCandidate.byte_size, estimate);
  const canStart = snapshot?.initialized === true
    && catalog.status === "success"
    && isOnline
    && !clearing
    && actionPending === null
    && !hasActiveDownload
    && nextCandidate !== undefined
    && enoughSpace;
  const batch = snapshot?.batchProgress ?? null;
  const batchPercent = batch ? progressPercent(batch.displayedBytes, batch.totalBytes) : null;
  const quotaExceeded = snapshot?.currentErrorCode === "storage_quota_exceeded" || (nextCandidate !== undefined && !enoughSpace);
  const hasFailedDownloads = batch?.state === "failed" || snapshot?.records.some((record) => record.status === "failed") === true;

  const startDownload = useCallback(() => {
    if (!canStart) return;
    setActionError(null);
    setActionPending("start");
    void enqueueCatalogAndStart(eligibleVideos).then(
      () => setActionError(null),
      () => setActionError("start"),
    ).finally(() => setActionPending(null));
  }, [canStart, eligibleVideos, enqueueCatalogAndStart]);

  const clearLibrary = useCallback(() => {
    if (!window.confirm("Вы точно хотите удалить все скачанные Reels?")) return;
    setActionError(null);
    setActionPending("clear");
    setClearing(true);
    invalidateCatalogRequest();
    void cancelAndClear().then(
      () => {
        setActionError(null);
        refreshEstimate();
        if (isNetworkOnline) loadCatalog();
      },
      () => setActionError("clear"),
    ).finally(() => {
      setClearing(false);
      setActionPending(null);
    });
  }, [cancelAndClear, invalidateCatalogRequest, isNetworkOnline, loadCatalog, refreshEstimate]);

  const visualStoragePercent = estimate.isAvailable && estimate.usage !== null && estimate.usage > 0 && getStorageUsagePresentation(estimate).percent !== null
    ? Math.max(1, getStorageUsagePresentation(estimate).percent!)
    : 0;
  const storagePresentation = getStorageUsagePresentation(estimate);

  return (
    <main className="mx-auto flex min-h-dvh max-w-lg flex-col px-5 pt-[calc(env(safe-area-inset-top)+2rem)] pb-[calc(var(--app-bottom-navigation-space)+1.5rem)]">
      <section className="space-y-7">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-950">Offline Reels</h1>
        <p className="text-sm font-medium text-slate-600" aria-live="polite">{isOnline ? "Онлайн" : "Нет подключения"}</p>

        <section aria-labelledby="storage-heading" className="space-y-3">
          <h2 id="storage-heading" className="sr-only">Заполненность хранилища</h2>
          <p className="text-base font-medium text-slate-800">{storagePresentation.label}</p>
          <div
            className="h-2 overflow-hidden rounded-full bg-slate-200"
            role="progressbar"
            aria-label="Заполненность хранилища"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={storagePresentation.percent ?? undefined}
          >
            <div className="h-full rounded-full bg-slate-900 transition-[width] motion-reduce:transition-none" style={{ width: `${visualStoragePercent}%` }} />
          </div>
        </section>

        {catalog.status === "error" && isOnline ? (
          <div className="space-y-3" role="alert">
            <p>Не удалось загрузить каталог Reels.</p>
            <button className="min-h-11 rounded-xl border border-slate-300 px-4 py-2 font-medium" type="button" onClick={loadCatalog}>
              Повторить
            </button>
          </div>
        ) : null}

        {batch?.state === "active" && batchPercent !== null ? (
          <section className="space-y-3" aria-labelledby="download-progress-heading">
            <p id="download-progress-heading" className="font-medium" aria-live="polite">Загрузка Reels — {batchPercent}%</p>
            <div className="h-2 overflow-hidden rounded-full bg-slate-200" role="progressbar" aria-label="Загрузка Reels" aria-valuemin={0} aria-valuemax={100} aria-valuenow={batchPercent}>
              <div className="h-full rounded-full bg-slate-900 transition-[width] motion-reduce:transition-none" style={{ width: `${batchPercent}%` }} />
            </div>
            <button className="min-h-11 rounded-xl border border-slate-300 px-4 py-2 font-medium" type="button" onClick={() => void cancelBatch()}>
              Отменить загрузку
            </button>
          </section>
        ) : null}

        {hasFailedDownloads && batch?.state !== "active" ? (
          <button className="min-h-11 rounded-xl border border-slate-300 px-4 py-2 font-medium disabled:cursor-not-allowed disabled:opacity-50" type="button" disabled={!canStart} onClick={startDownload}>
            Повторить
          </button>
        ) : null}

        {quotaExceeded ? <p role="alert" className="text-sm font-medium text-amber-800">Память уже заполнена. Больше Reels скачать нельзя.</p> : null}
        {actionError === "start" ? <p role="alert" className="text-sm font-medium text-red-800">Не удалось начать загрузку Reels. Попробуйте ещё раз.</p> : null}
        {actionError === "clear" ? <p role="alert" className="text-sm font-medium text-red-800">Не удалось полностью очистить библиотеку. Попробуйте ещё раз.</p> : null}

        <button className="min-h-12 w-full rounded-xl bg-slate-950 px-5 py-3 font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-400" type="button" disabled={!canStart} onClick={startDownload}>
          Загрузить Reels
        </button>
        <button className="min-h-11 w-full rounded-xl border border-red-300 px-5 py-3 font-medium text-red-800 disabled:cursor-not-allowed disabled:opacity-50" type="button" disabled={clearing || snapshot?.clearing === true || actionPending !== null} onClick={clearLibrary}>
          Очистить библиотеку
        </button>
      </section>
      <AppBottomNavigation activeRoute="home" />
    </main>
  );
}

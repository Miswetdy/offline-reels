"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { VerticalVideoFeed, type VerticalVideoFeedItem } from "./vertical-video-feed";
import { getOfflineErrorMessage, toOfflineStorageError } from "../lib/offline/errors";
import { getMediaCacheKey } from "../lib/offline/media-cache";
import { createOfflinePlaybackSource } from "../lib/offline/playback-source";
import { reconcileOfflineLibrary } from "../lib/offline/reconciliation";
import { listCompletedOfflineVideos } from "../lib/offline/repository";
import { getStorageEstimate, type LocalStorageEstimate } from "../lib/offline/storage";
import type { OfflineVideoRecord } from "../lib/offline/types";

type OfflineLibraryState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; records: OfflineVideoRecord[]; estimate: LocalStorageEstimate };

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

  useEffect(() => {
    let disposed = false;
    void (async () => {
      try {
        await reconcileOfflineLibrary();
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

  const resolveMediaSource = useCallback(
    (item: VerticalVideoFeedItem) => createOfflinePlaybackSource(item.id),
    [],
  );

  const feedItems = useMemo<VerticalVideoFeedItem[]>(() => {
    if (state.status !== "success") return [];
    return state.records.map((record) => ({
      id: record.id,
      title: record.title,
      mediaUrl: record.cacheKey ?? getMediaCacheKey(record.id),
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
        <button className="rounded bg-slate-900 px-4 py-2 text-white" type="button" onClick={() => {
          setState({ status: "loading" });
          setReloadAttempt((value) => value + 1);
        }}>
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

  return (
    <>
      <VerticalVideoFeed items={feedItems} resolveMediaSource={resolveMediaSource} />
      <aside className="fixed left-4 top-4 z-20 max-w-[calc(100%-8rem)] rounded bg-black/75 p-3 text-sm text-white" aria-label="Offline library summary">
        <p>Офлайн: {state.records.length} видео · {formatBytes(librarySize)}</p>
        {state.estimate.isAvailable ? (
          <p className="mt-1">Хранилище браузера (примерно): {state.estimate.usage === null ? "недоступно" : formatBytes(state.estimate.usage)}{state.estimate.quota === null ? "" : ` / ${formatBytes(state.estimate.quota)}`}</p>
        ) : <p className="mt-1">Хранилище браузера (примерно): недоступно</p>}
        <Link className="mt-2 inline-block underline" href="/videos">К онлайн-ленте</Link>
      </aside>
    </>
  );
}

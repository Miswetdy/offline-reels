"use client";

import { useMemo, useState } from "react";

import { useOfflineDownloads } from "../hooks/use-offline-downloads";
import type { Video } from "../lib/api/videos";
import type { OfflineErrorCode, OfflineVideoStatus } from "../lib/offline/types";

const EMPTY_RECORDS: NonNullable<ReturnType<typeof useOfflineDownloads>["snapshot"]>["records"] = [];

type OfflineDownloadControlsProps = {
  videos: Video[];
  activeVideoId: string | null;
};

function statusLabel(status: OfflineVideoStatus | undefined): string {
  switch (status) {
    case "queued":
      return "В очереди";
    case "downloading":
      return "Скачивается";
    case "completed":
      return "Скачано";
    case "failed":
      return "Ошибка загрузки";
    default:
      return "Не скачано";
  }
}

function errorLabel(code: OfflineErrorCode | null): string | null {
  switch (code) {
    case "network_error":
      return "Не удалось скачать видео. Проверьте подключение.";
    case "storage_quota_exceeded":
      return "Недостаточно места. Удалите часть данных и повторите.";
    case "unsupported_content_type":
      return "Формат видео не поддерживается.";
    case "content_length_mismatch":
    case "byte_size_mismatch":
      return "Файл скачался некорректно. Повторите загрузку.";
    case "download_aborted":
      return "Загрузка отменена.";
    case "download_interrupted":
      return "Загрузка была прервана. Нажмите «Повторить».";
    case "cache_write_failed":
      return "Не удалось сохранить видео на устройстве.";
    case "cache_validation_failed":
      return "Сохранённый файл повреждён. Повторите загрузку.";
    default:
      return code ? "Не удалось сохранить видео на устройстве." : null;
  }
}

function batchCandidates(videos: Video[], activeVideoId: string | null, statuses: Map<string, OfflineVideoStatus>): Video[] {
  const activeIndex = Math.max(0, videos.findIndex((video) => video.id === activeVideoId));
  return videos
    .slice(activeIndex)
    .filter((video) => statuses.get(video.id) === undefined)
    .slice(0, 5);
}

export function OfflineDownloadControls({ videos, activeVideoId }: OfflineDownloadControlsProps) {
  const { snapshot, enqueueAndStart, enqueueManyAndStart, retryAndStart, continueDownloads, abortActive } = useOfflineDownloads();
  const [batchMessage, setBatchMessage] = useState<string | null>(null);
  const records = snapshot?.records ?? EMPTY_RECORDS;
  const statuses = useMemo(() => new Map(records.map((record) => [record.id, record.status])), [records]);
  const activeVideo = videos.find((video) => video.id === activeVideoId) ?? videos[0];
  const activeStatus = activeVideo ? statuses.get(activeVideo.id) : undefined;
  const candidates = batchCandidates(videos, activeVideo?.id ?? null, statuses);
  const queueError = errorLabel(snapshot?.currentErrorCode ?? null);
  const recordError = activeVideo
    ? errorLabel(records.find((record) => record.id === activeVideo.id)?.lastErrorCode ?? null)
    : null;

  if (!snapshot || !activeVideo) return null;

  return (
    <aside className="fixed left-4 top-4 z-20 max-w-[calc(100%-8rem)] rounded bg-black/75 p-3 text-sm text-white" aria-label="Offline downloads">
      <p>Офлайн: {snapshot.completedCount} видео · {snapshot.completedBytes.toLocaleString()} Б</p>
      <p className="mt-1" aria-live="polite">{snapshot.online ? "Онлайн" : "Нет подключения"} · {statusLabel(activeStatus)}</p>
      {snapshot.currentProgress ? (
        <p className="mt-1" aria-live="polite">
          {snapshot.currentProgress.downloadedBytes.toLocaleString()} Б
          {snapshot.currentProgress.totalBytes !== null
            ? ` / ${snapshot.currentProgress.totalBytes.toLocaleString()} Б (${Math.round(snapshot.currentProgress.percent ?? 0)}%)`
            : " · загрузка…"}
        </p>
      ) : null}
      <p className="mt-1">В очереди: {snapshot.queuedCount}</p>
      {queueError ?? recordError ? <p className="mt-1 text-amber-200" role="alert">{queueError ?? recordError}</p> : null}
      <div className="mt-2 flex flex-wrap gap-2">
        {activeStatus === "failed" ? (
          <button
            className="rounded bg-white px-2 py-1 text-slate-950"
            type="button"
            onClick={() => void retryAndStart(activeVideo.id).catch(() => undefined)}
          >
            Повторить
          </button>
        ) : (
          <button
            className="rounded bg-white px-2 py-1 text-slate-950 disabled:opacity-50"
            type="button"
            disabled={!snapshot.online || activeStatus !== undefined}
            onClick={() => void enqueueAndStart(activeVideo).catch(() => undefined)}
          >
            Скачать текущий
          </button>
        )}
        <button
          className="rounded bg-slate-700 px-2 py-1 disabled:opacity-50"
          type="button"
          disabled={!snapshot.online || candidates.length === 0}
          onClick={() => {
            void enqueueManyAndStart(candidates)
              .then((count) => setBatchMessage(`Добавлено: ${count}`))
              .catch(() => undefined);
          }}
        >
          Скачать следующие 5
        </button>
        {snapshot.paused && snapshot.queuedCount > 0 ? (
          <button className="rounded bg-slate-700 px-2 py-1" type="button" disabled={!snapshot.online} onClick={continueDownloads}>
            Продолжить загрузку
          </button>
        ) : null}
        {snapshot.activeVideoId ? (
          <button className="rounded bg-amber-200 px-2 py-1 text-slate-950" type="button" onClick={abortActive}>
            Отменить
          </button>
        ) : null}
      </div>
      {batchMessage ? <p className="mt-1" aria-live="polite">{batchMessage}</p> : null}
    </aside>
  );
}

import { getVideoStreamUrl, type Video } from "../api/videos";
import { OfflineStorageError, toOfflineStorageError } from "./errors";
import { deleteCachedVideo, getMediaCacheKey, putCachedVideoOwnedResponse, validateCachedVideo } from "./media-cache";
import { getOfflineVideo, putOfflineVideo, updateOfflineVideo } from "./repository";
import { getStorageEstimate, hasEstimatedSpaceForDownload } from "./storage";
import type { OfflineErrorCode, OfflineVideoRecord } from "./types";
import { isAllowedVideoContentType } from "./validation";
import { normalizeVideoId } from "./media-key";

export type DownloadProgress = {
  videoId: string;
  downloadedBytes: number;
  totalBytes: number | null;
  percent: number | null;
};

export type DownloadVideoOptions = {
  video: Video;
  signal: AbortSignal;
  onProgress?: (progress: DownloadProgress) => void;
};

export type DownloaderDependencies = {
  fetchImplementation: typeof fetch;
  getStorageEstimate: typeof getStorageEstimate;
  hasEstimatedSpaceForDownload: typeof hasEstimatedSpaceForDownload;
  getOfflineVideo: typeof getOfflineVideo;
  putOfflineVideo: typeof putOfflineVideo;
  updateOfflineVideo: typeof updateOfflineVideo;
  deleteCachedVideo: typeof deleteCachedVideo;
  putCachedVideoOwnedResponse: typeof putCachedVideoOwnedResponse;
  validateCachedVideo: typeof validateCachedVideo;
  getStreamUrl: typeof getVideoStreamUrl;
  now: () => string;
  progressIntervalMs: number;
};

const DEFAULT_DEPENDENCIES: DownloaderDependencies = {
  fetchImplementation: (...args) => fetch(...args),
  getStorageEstimate,
  hasEstimatedSpaceForDownload,
  getOfflineVideo,
  putOfflineVideo,
  updateOfflineVideo,
  deleteCachedVideo,
  putCachedVideoOwnedResponse,
  validateCachedVideo,
  getStreamUrl: getVideoStreamUrl,
  now: () => new Date().toISOString(),
  progressIntervalMs: 125,
};

function safeMessage(code: OfflineErrorCode): string {
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
      return "Не удалось сохранить видео на устройстве.";
  }
}

function parseContentLength(header: string | null): number | null {
  if (header === null) return null;
  if (!/^(0|[1-9]\d*)$/.test(header)) {
    throw new OfflineStorageError("content_length_mismatch");
  }
  const value = Number(header);
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new OfflineStorageError("content_length_mismatch");
  }
  return value;
}

function assertVideoMetadata(video: Video): void {
  normalizeVideoId(video.id);
  if (video.title.trim().length === 0 || !isAllowedVideoContentType(video.content_type)) {
    throw new OfflineStorageError("unsupported_content_type");
  }
  if (!Number.isSafeInteger(video.byte_size) || video.byte_size <= 0 || !Number.isFinite(Date.parse(video.created_at))) {
    throw new OfflineStorageError("byte_size_mismatch");
  }
}

function createQueuedRecord(video: Video, timestamp: string): OfflineVideoRecord {
  return {
    id: normalizeVideoId(video.id),
    title: video.title,
    contentType: "video/mp4",
    byteSize: video.byte_size,
    createdAt: video.created_at,
    status: "queued",
    downloadedBytes: 0,
    downloadedAt: null,
    cacheKey: null,
    lastErrorCode: null,
    lastErrorMessage: null,
    failedAt: null,
    lastWatchedAt: null,
    updatedAt: timestamp,
  };
}

function isAbort(error: unknown, signal: AbortSignal): boolean {
  return signal.aborted || (error instanceof DOMException && error.name === "AbortError");
}

function normalizeDownloadError(error: unknown, signal: AbortSignal): OfflineStorageError {
  if (isAbort(error, signal)) return new OfflineStorageError("download_aborted", error);
  if (error instanceof TypeError) return new OfflineStorageError("network_error", error);
  return toOfflineStorageError(error);
}

function createProgressEmitter(
  videoId: string,
  totalBytes: number | null,
  onProgress: DownloadVideoOptions["onProgress"],
  intervalMs: number,
) {
  let lastEmission = -Infinity;
  let downloadedBytes = 0;
  const emit = (force = false) => {
    if (!onProgress) return;
    const now = Date.now();
    if (!force && now - lastEmission < intervalMs) return;
    lastEmission = now;
    onProgress({
      videoId,
      downloadedBytes,
      totalBytes,
      percent: totalBytes && totalBytes > 0 ? (downloadedBytes / totalBytes) * 100 : null,
    });
  };
  return {
    add(chunk: Uint8Array) {
      downloadedBytes += chunk.byteLength;
      emit();
    },
    finish() {
      emit(true);
      return downloadedBytes;
    },
  };
}

async function markFailed(
  videoId: string,
  error: OfflineStorageError,
  dependencies: DownloaderDependencies,
): Promise<void> {
  const updated = await dependencies.updateOfflineVideo(videoId, {
    status: "failed",
    downloadedBytes: 0,
    downloadedAt: null,
    cacheKey: null,
    lastErrorCode: error.code,
    lastErrorMessage: safeMessage(error.code),
    failedAt: dependencies.now(),
  });
  if (!updated) {
    throw new OfflineStorageError("unknown_error");
  }
}

export async function downloadVideoForOffline(
  options: DownloadVideoOptions,
  partialDependencies: Partial<DownloaderDependencies> = {},
): Promise<OfflineVideoRecord> {
  const dependencies = { ...DEFAULT_DEPENDENCIES, ...partialDependencies };
  const { video, signal } = options;
  assertVideoMetadata(video);
  const videoId = normalizeVideoId(video.id);
  const existing = await dependencies.getOfflineVideo(videoId);

  // A view tombstone is durable even if a previous cache write or fetch
  // finishes late. It is never eligible to re-enter the local library.
  if (existing?.viewedAt || existing?.deletionState === "deleted") {
    throw new OfflineStorageError("download_aborted");
  }

  if (existing?.status === "completed") {
    const validation = await dependencies.validateCachedVideo(videoId, existing);
    if (validation.valid) return existing;
    await dependencies.deleteCachedVideo(videoId).catch(() => undefined);
  }

  if (!existing) {
    await dependencies.putOfflineVideo(createQueuedRecord(video, dependencies.now()));
  }

  const estimate = await dependencies.getStorageEstimate();
  if (!dependencies.hasEstimatedSpaceForDownload(video.byte_size, estimate)) {
    const quotaError = new OfflineStorageError("storage_quota_exceeded");
    await markFailed(videoId, quotaError, dependencies);
    throw quotaError;
  }

  await dependencies.updateOfflineVideo(videoId, {
    title: video.title,
    contentType: "video/mp4",
    byteSize: video.byte_size,
    createdAt: video.created_at,
    status: "downloading",
    downloadedBytes: 0,
    downloadedAt: null,
    cacheKey: null,
    lastErrorCode: null,
    lastErrorMessage: null,
    failedAt: null,
  });

  try {
    const response = await dependencies.fetchImplementation(dependencies.getStreamUrl(videoId), {
      cache: "no-store",
      signal,
    });
    if (response.status !== 200) throw new OfflineStorageError("http_error");
    if (!response.body) throw new OfflineStorageError("response_body_missing");
    if (!isAllowedVideoContentType(response.headers.get("content-type") ?? "")) {
      throw new OfflineStorageError("unsupported_content_type");
    }

    const contentLength = parseContentLength(response.headers.get("content-length"));
    if (contentLength !== null && contentLength !== video.byte_size) {
      throw new OfflineStorageError("content_length_mismatch");
    }

    const progress = createProgressEmitter(videoId, contentLength, options.onProgress, dependencies.progressIntervalMs);
    const transformedStream = response.body.pipeThrough(
      new TransformStream<Uint8Array, Uint8Array>({
        transform(chunk, controller) {
          if (signal.aborted) throw new DOMException("The download was aborted.", "AbortError");
          progress.add(chunk);
          controller.enqueue(chunk);
        },
      }),
    );
    const ownedResponse = new Response(transformedStream, {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
    });

    await dependencies.putCachedVideoOwnedResponse(videoId, ownedResponse);
    const actualByteSize = progress.finish();
    if (actualByteSize === 0 || actualByteSize !== video.byte_size) {
      throw new OfflineStorageError("byte_size_mismatch");
    }

    const cacheKey = getMediaCacheKey(videoId);
    const validation = await dependencies.validateCachedVideo(videoId, {
      cacheKey,
      contentType: "video/mp4",
      byteSize: video.byte_size,
    });
    if (!validation.valid) throw new OfflineStorageError("cache_validation_failed");

    const beforeCommit = await dependencies.getOfflineVideo(videoId);
    if (beforeCommit?.viewedAt || beforeCommit?.deletionState === "deleted") {
      await dependencies.deleteCachedVideo(videoId).catch(() => undefined);
      throw new OfflineStorageError("download_aborted");
    }
    const completed = await dependencies.updateOfflineVideo(videoId, {
      status: "completed",
      downloadedBytes: actualByteSize,
      downloadedAt: dependencies.now(),
      cacheKey,
      lastErrorCode: null,
      lastErrorMessage: null,
      failedAt: null,
    });
    if (!completed) throw new OfflineStorageError("unknown_error");
    return completed;
  } catch (error) {
    const normalized = normalizeDownloadError(error, signal);
    await dependencies.deleteCachedVideo(videoId).catch(() => undefined);
    const current = await dependencies.getOfflineVideo(videoId);
    if (current?.viewedAt || current?.deletionState === "deleted") {
      // A concurrent Stage 9 tombstone wins over a stale downloader. Never
      // turn it into a retryable failed record.
      throw normalized;
    }
    try {
      await markFailed(videoId, normalized, dependencies);
    } catch (metadataError) {
      throw toOfflineStorageError(metadataError);
    }
    throw normalized;
  }
}

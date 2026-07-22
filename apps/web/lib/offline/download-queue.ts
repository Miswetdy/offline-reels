import type { Video } from "../api/videos";
import { toOfflineStorageError } from "./errors";
import { downloadVideoForOffline, type DownloadProgress } from "./downloader";
import { reconcileOfflineLibrary } from "./reconciliation";
import {
  calculateCompletedLibrarySize,
  deleteOfflineVideo,
  getOfflineVideo,
  listOfflineVideos,
  putOfflineVideo,
  updateOfflineVideo,
} from "./repository";
import { normalizeVideoId } from "./media-key";
import type { OfflineErrorCode, OfflineVideoRecord } from "./types";

export type DownloadQueueSnapshot = {
  activeVideoId: string | null;
  paused: boolean;
  queuedCount: number;
  completedCount: number;
  completedBytes: number;
  currentProgress: DownloadProgress | null;
  currentErrorCode: OfflineErrorCode | null;
  online: boolean;
  records: OfflineVideoRecord[];
};

type DownloadQueueDependencies = {
  downloadVideoForOffline: typeof downloadVideoForOffline;
  reconcileOfflineLibrary: typeof reconcileOfflineLibrary;
  getOfflineVideo: typeof getOfflineVideo;
  listOfflineVideos: typeof listOfflineVideos;
  putOfflineVideo: typeof putOfflineVideo;
  updateOfflineVideo: typeof updateOfflineVideo;
  deleteOfflineVideo: typeof deleteOfflineVideo;
  calculateCompletedLibrarySize: typeof calculateCompletedLibrarySize;
  now: () => string;
  isOnline: () => boolean;
  addNetworkListener: (event: "online" | "offline", listener: () => void) => () => void;
};

const DEFAULT_DEPENDENCIES: DownloadQueueDependencies = {
  downloadVideoForOffline,
  reconcileOfflineLibrary,
  getOfflineVideo,
  listOfflineVideos,
  putOfflineVideo,
  updateOfflineVideo,
  deleteOfflineVideo,
  calculateCompletedLibrarySize,
  now: () => new Date().toISOString(),
  isOnline: () => typeof navigator === "undefined" || navigator.onLine,
  addNetworkListener: (event, listener) => {
    if (typeof window === "undefined") return () => undefined;
    window.addEventListener(event, listener);
    return () => window.removeEventListener(event, listener);
  },
};

function toQueueRecord(video: Video, timestamp: string): OfflineVideoRecord {
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

function emptySnapshot(online: boolean): DownloadQueueSnapshot {
  return {
    activeVideoId: null,
    paused: true,
    queuedCount: 0,
    completedCount: 0,
    completedBytes: 0,
    currentProgress: null,
    currentErrorCode: null,
    online,
    records: [],
  };
}

export class OfflineDownloadQueue {
  private readonly dependencies: DownloadQueueDependencies;
  private readonly listeners = new Set<() => void>();
  private readonly unsubscribeNetwork: Array<() => void>;
  private snapshot: DownloadQueueSnapshot;
  private activeController: AbortController | null = null;
  private pumpPromise: Promise<void> | null = null;
  private initializationPromise: Promise<void> | null = null;

  constructor(partialDependencies: Partial<DownloadQueueDependencies> = {}) {
    this.dependencies = { ...DEFAULT_DEPENDENCIES, ...partialDependencies };
    this.snapshot = emptySnapshot(this.dependencies.isOnline());
    this.unsubscribeNetwork = [
      this.dependencies.addNetworkListener("offline", () => {
        this.snapshot = { ...this.snapshot, online: false, paused: true };
        this.activeController?.abort();
        this.emit();
      }),
      this.dependencies.addNetworkListener("online", () => {
        this.snapshot = { ...this.snapshot, online: true };
        this.emit();
      }),
    ];
  }

  getSnapshot = (): DownloadQueueSnapshot => this.snapshot;

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  async initialize(): Promise<void> {
    if (!this.initializationPromise) {
      this.initializationPromise = (async () => {
        await this.dependencies.reconcileOfflineLibrary();
        await this.refreshRecords();
      })();
    }
    return this.initializationPromise;
  }

  async enqueue(video: Video): Promise<boolean> {
    const videoId = normalizeVideoId(video.id);
    const existing = await this.dependencies.getOfflineVideo(videoId);
    if (existing?.status === "completed" || existing?.status === "queued" || existing?.status === "downloading") {
      return false;
    }
    if (existing?.status === "failed") return false;

    await this.dependencies.putOfflineVideo(toQueueRecord(video, this.dependencies.now()));
    await this.refreshRecords();
    return true;
  }

  async enqueueMany(videos: Video[]): Promise<number> {
    let enqueued = 0;
    for (const video of videos) {
      if (await this.enqueue(video)) enqueued += 1;
    }
    return enqueued;
  }

  async retry(videoId: string): Promise<boolean> {
    const id = normalizeVideoId(videoId);
    const record = await this.dependencies.getOfflineVideo(id);
    if (!record || record.status !== "failed") return false;
    await this.dependencies.updateOfflineVideo(id, {
      status: "queued",
      downloadedBytes: 0,
      downloadedAt: null,
      cacheKey: null,
      lastErrorCode: null,
      lastErrorMessage: null,
      failedAt: null,
    });
    await this.refreshRecords();
    return true;
  }

  async removeQueued(videoId: string): Promise<boolean> {
    const id = normalizeVideoId(videoId);
    const record = await this.dependencies.getOfflineVideo(id);
    if (!record || record.status !== "queued") return false;
    await this.dependencies.deleteOfflineVideo(id);
    await this.refreshRecords();
    return true;
  }

  async start(): Promise<void> {
    await this.initialize();
    if (!this.dependencies.isOnline()) {
      this.snapshot = { ...this.snapshot, online: false, paused: true };
      this.emit();
      return;
    }
    this.snapshot = { ...this.snapshot, online: true, paused: false, currentErrorCode: null };
    this.emit();
    if (!this.pumpPromise) {
      this.pumpPromise = this.pump().finally(() => {
        this.pumpPromise = null;
      });
    }
    await this.pumpPromise;
  }

  pause(): void {
    this.snapshot = { ...this.snapshot, paused: true };
    this.emit();
  }

  abortActive(): void {
    if (!this.activeController) return;
    this.snapshot = { ...this.snapshot, paused: true };
    this.activeController.abort();
    this.emit();
  }

  dispose(): void {
    this.abortActive();
    this.unsubscribeNetwork.forEach((unsubscribe) => unsubscribe());
    this.listeners.clear();
  }

  private async pump(): Promise<void> {
    while (!this.snapshot.paused && this.dependencies.isOnline()) {
      const records = await this.dependencies.listOfflineVideos();
      const next = records.find((record) => record.status === "queued");
      if (!next) break;

      const controller = new AbortController();
      this.activeController = controller;
      this.snapshot = {
        ...this.snapshot,
        activeVideoId: next.id,
        currentProgress: { videoId: next.id, downloadedBytes: 0, totalBytes: null, percent: null },
        currentErrorCode: null,
      };
      this.emit();

      try {
        await this.dependencies.downloadVideoForOffline({
          video: {
            id: next.id,
            title: next.title,
            content_type: next.contentType,
            byte_size: next.byteSize,
            created_at: next.createdAt,
          },
          signal: controller.signal,
          onProgress: (progress) => {
            if (this.activeController !== controller) return;
            this.snapshot = { ...this.snapshot, currentProgress: progress };
            this.emit();
          },
        });
      } catch (error) {
        const normalized = toOfflineStorageError(error);
        const shouldPause = normalized.code === "storage_quota_exceeded" || normalized.code === "download_aborted";
        this.snapshot = {
          ...this.snapshot,
          paused: shouldPause || this.snapshot.paused,
          currentErrorCode: normalized.code,
        };
      } finally {
        if (this.activeController === controller) this.activeController = null;
        this.snapshot = { ...this.snapshot, activeVideoId: null, currentProgress: null };
        await this.refreshRecords();
      }
    }
    this.snapshot = { ...this.snapshot, activeVideoId: null, currentProgress: null, online: this.dependencies.isOnline() };
    this.emit();
  }

  private async refreshRecords(): Promise<void> {
    const records = await this.dependencies.listOfflineVideos();
    const completedBytes = await this.dependencies.calculateCompletedLibrarySize();
    this.snapshot = {
      ...this.snapshot,
      records,
      queuedCount: records.filter((record) => record.status === "queued").length,
      completedCount: records.filter((record) => record.status === "completed").length,
      completedBytes,
      online: this.dependencies.isOnline(),
    };
    this.emit();
  }

  private emit(): void {
    this.listeners.forEach((listener) => listener());
  }
}

const GLOBAL_QUEUE_KEY = "__offlineReelsDownloadQueueV1";

export function getOfflineDownloadQueue(): OfflineDownloadQueue {
  if (typeof window === "undefined") {
    throw new Error("OfflineDownloadQueue is only available in the browser.");
  }
  const globalWindow = window as Window & { [GLOBAL_QUEUE_KEY]?: OfflineDownloadQueue };
  globalWindow[GLOBAL_QUEUE_KEY] ??= new OfflineDownloadQueue();
  return globalWindow[GLOBAL_QUEUE_KEY];
}

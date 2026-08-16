import type { Video } from "../api/videos";
import { toOfflineStorageError } from "./errors";
import { downloadVideoForOffline, type DownloadProgress } from "./downloader";
import { clearOfflineLibrary } from "./library-management";
import { deleteCachedVideo } from "./media-cache";
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
  initialized: boolean;
  clearing: boolean;
  batchProgress: DownloadBatchProgress | null;
  records: OfflineVideoRecord[];
};

export type DownloadBatchProgress = {
  totalBytes: number;
  completedBytes: number;
  displayedBytes: number;
  state: "active" | "failed" | "completed";
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
  clearOfflineLibrary: typeof clearOfflineLibrary;
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
  clearOfflineLibrary,
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
    initialized: false,
    clearing: false,
    batchProgress: null,
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
  private controlTail: Promise<void> = Promise.resolve();
  private clearing = false;
  private batchVideoIds: Set<string> | null = null;
  private readonly cancelledActiveVideoIds = new Set<string>();

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
        this.snapshot = { ...this.snapshot, initialized: true };
        this.emit();
      })();
    }
    return this.initializationPromise;
  }

  /**
   * Re-read durable library metadata after an external lifecycle operation
   * (for example Stage 9's delayed Cache deletion). This intentionally does
   * not mutate queued work or Cache Storage; it only refreshes the in-memory
   * projection used by the reserve controller and UI.
   */
  async refreshFromStorage(): Promise<void> {
    await this.initialize();
    await this.refreshRecords();
  }

  async enqueue(video: Video): Promise<boolean> {
    return this.runControlled(async () => this.enqueueUnlocked(video));
  }

  async enqueueMany(videos: Video[]): Promise<number> {
    return this.runControlled(async () => {
      let enqueued = 0;
      for (const video of videos) {
        if (await this.enqueueUnlocked(video)) enqueued += 1;
      }
      return enqueued;
    });
  }

  async retry(videoId: string): Promise<boolean> {
    return this.runControlled(async () => this.retryUnlocked(videoId));
  }

  async removeQueued(videoId: string): Promise<boolean> {
    return this.runControlled(async () => {
      const id = normalizeVideoId(videoId);
      const record = await this.dependencies.getOfflineVideo(id);
      if (!record || record.status !== "queued") return false;
      await this.dependencies.deleteOfflineVideo(id);
      await this.refreshRecords();
      return true;
    });
  }

  async enqueueCatalogAndStart(videos: Video[]): Promise<number> {
    await this.initialize();
    const queued = await this.runControlled(async () => {
      const uniqueVideos = new Map(videos.map((video) => [normalizeVideoId(video.id), video]));
      const candidates: Video[] = [];
      for (const video of uniqueVideos.values()) {
        const existing = await this.dependencies.getOfflineVideo(video.id);
        if (existing?.viewedAt || existing?.deletionState === "deleted" || existing?.status === "completed" || existing?.status === "queued" || existing?.status === "downloading") continue;
        if (existing?.status === "failed") {
          if (await this.retryUnlocked(video.id)) candidates.push(video);
          continue;
        }
        if (await this.enqueueUnlocked(video)) candidates.push(video);
      }
      this.batchVideoIds = new Set(candidates.map((video) => video.id));
      this.snapshot = {
        ...this.snapshot,
        batchProgress: candidates.length === 0 ? null : {
          totalBytes: candidates.reduce((total, video) => total + video.byte_size, 0),
          completedBytes: 0,
          displayedBytes: 0,
          state: "active",
        },
      };
      this.emit();
      return candidates.length;
    });
    if (queued > 0) void this.start().catch(() => undefined);
    return queued;
  }

  async enqueueReserveAndStart(videos: Video[], limit: number): Promise<number> {
    if (!Number.isInteger(limit) || limit < 1) return 0;
    await this.initialize();
    const queued = await this.runControlled(async () => {
      const uniqueVideos = new Map(videos.map((video) => [normalizeVideoId(video.id), video]));
      const candidates: Video[] = [];
      for (const video of uniqueVideos.values()) {
        if (candidates.length >= limit) break;
        const existing = await this.dependencies.getOfflineVideo(video.id);
        if (existing?.viewedAt || existing?.deletionState === "deleted" || existing?.status === "completed" || existing?.status === "queued" || existing?.status === "downloading") continue;
        if (existing?.status === "failed") {
          if (await this.retryUnlocked(video.id)) candidates.push(video);
          continue;
        }
        if (await this.enqueueUnlocked(video)) candidates.push(video);
      }
      this.batchVideoIds = new Set(candidates.map((video) => video.id));
      this.snapshot = {
        ...this.snapshot,
        batchProgress: candidates.length === 0 ? null : {
          totalBytes: candidates.reduce((total, video) => total + video.byte_size, 0),
          completedBytes: 0,
          displayedBytes: 0,
          state: "active",
        },
      };
      this.emit();
      return candidates.length;
    });
    if (queued > 0) await this.start();
    return queued;
  }

  async cancelAndClear(): Promise<void> {
    await this.runControlled(async () => {
      this.clearing = true;
      this.snapshot = { ...this.snapshot, clearing: true, paused: true, currentErrorCode: null };
      this.activeController?.abort();
      this.emit();
    });

    try {
      await this.pumpPromise;
      await this.dependencies.clearOfflineLibrary();
      this.batchVideoIds = null;
      this.snapshot = { ...emptySnapshot(this.dependencies.isOnline()), initialized: true, clearing: true };
      await this.refreshRecords();
    } catch (error) {
      // Cleanup can partially complete (for example, media cache deletion can
      // succeed before IndexedDB cleanup fails). Refresh the observable state
      // without retrying destructive work, then preserve the original error.
      await this.refreshRecords().catch(() => undefined);
      throw error;
    } finally {
      this.clearing = false;
      this.snapshot = { ...this.snapshot, clearing: false, paused: true };
      this.emit();
    }
  }

  async start(): Promise<void> {
    await this.initialize();
    if (this.clearing) return;
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

      if (this.clearing) break;
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
            if (this.activeController !== controller || this.clearing) return;
            this.snapshot = { ...this.snapshot, currentProgress: progress };
            this.updateBatchProgress();
            this.emit();
          },
        });
        if (this.cancelledActiveVideoIds.delete(next.id)) {
          await deleteCachedVideo(next.id).catch(() => undefined);
          await this.dependencies.deleteOfflineVideo(next.id);
        }
      } catch (error) {
        const normalized = toOfflineStorageError(error);
        const shouldPause = normalized.code === "storage_quota_exceeded" || normalized.code === "download_aborted";
        this.snapshot = {
          ...this.snapshot,
          paused: shouldPause || this.snapshot.paused,
          currentErrorCode: normalized.code,
        };
      } finally {
        this.cancelledActiveVideoIds.delete(next.id);
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
    this.updateBatchProgress();
    this.emit();
  }

  async cancelBatch(): Promise<void> {
    await this.runControlled(async () => {
      if (this.snapshot.activeVideoId && this.batchVideoIds?.has(this.snapshot.activeVideoId)) {
        this.cancelledActiveVideoIds.add(this.snapshot.activeVideoId);
      }
      this.snapshot = { ...this.snapshot, paused: true };
      this.activeController?.abort();
      this.emit();
    });
    await this.pumpPromise;
    await this.runControlled(async () => {
      if (this.batchVideoIds) {
        for (const record of this.snapshot.records) {
          if (this.batchVideoIds.has(record.id) && record.status === "queued") {
            await this.dependencies.deleteOfflineVideo(record.id);
          }
        }
      }
      await this.refreshRecords();
    });
  }

  private async enqueueUnlocked(video: Video): Promise<boolean> {
    if (this.clearing) return false;
    const videoId = normalizeVideoId(video.id);
    const existing = await this.dependencies.getOfflineVideo(videoId);
    if (this.clearing || existing?.status === "completed" || existing?.status === "queued" || existing?.status === "downloading" || existing?.status === "failed") {
      return false;
    }
    await this.dependencies.putOfflineVideo(toQueueRecord(video, this.dependencies.now()));
    await this.refreshRecords();
    return true;
  }

  private async retryUnlocked(videoId: string): Promise<boolean> {
    if (this.clearing) return false;
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

  private runControlled<T>(operation: () => Promise<T>): Promise<T> {
    const previous = this.controlTail;
    let release!: () => void;
    this.controlTail = new Promise<void>((resolve) => { release = resolve; });
    return previous.then(operation).finally(release);
  }

  private updateBatchProgress(): void {
    const batch = this.snapshot.batchProgress;
    if (!batch || !this.batchVideoIds) return;
    const completedBytes = this.snapshot.records
      .filter((record) => this.batchVideoIds?.has(record.id) && record.status === "completed")
      .reduce((total, record) => total + record.byteSize, 0);
    const progress = this.snapshot.currentProgress;
    const currentBytes = progress && this.batchVideoIds.has(progress.videoId) ? progress.downloadedBytes : 0;
    const observedBytes = Math.min(batch.totalBytes, completedBytes + currentBytes);
    const hasPending = this.snapshot.records.some((record) => this.batchVideoIds?.has(record.id) && (record.status === "queued" || record.status === "downloading"));
    this.snapshot = {
      ...this.snapshot,
      batchProgress: {
        ...batch,
        completedBytes,
        displayedBytes: Math.max(batch.displayedBytes, observedBytes),
        state: hasPending || this.snapshot.activeVideoId !== null
          ? "active"
          : completedBytes === batch.totalBytes ? "completed" : "failed",
      },
    };
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

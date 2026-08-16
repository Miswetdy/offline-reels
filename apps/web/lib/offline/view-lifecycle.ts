import { getConfirmedViewedReels, refreshManagementSession, syncViewedReels } from "../api/management";
import { deleteCachedVideo } from "./media-cache";
import { getLocalReserve } from "./reserve-repository";
import { listOfflineVideos, markOfflineVideoViewed, updateOfflineVideo } from "./repository";
import { reconcileOfflineLibrary } from "./reconciliation";
import { lifecycleNow } from "./fixture-clock";

const MAX_SYNC_ATTEMPTS = 5;
const MAX_SYNC_BATCH = 50;

type Dependencies = {
  now: () => string;
  isOnline: () => boolean;
  markViewed: typeof markOfflineVideoViewed;
  list: typeof listOfflineVideos;
  update: typeof updateOfflineVideo;
  removeCache: typeof deleteCachedVideo;
  getReserve: typeof getLocalReserve;
  sync: typeof syncViewedReels;
  confirmed: typeof getConfirmedViewedReels;
  refreshSession: typeof refreshManagementSession;
  reconcile: typeof reconcileOfflineLibrary;
  schedule: (callback: () => void, milliseconds: number) => void;
};

const DEFAULT: Dependencies = {
  now: lifecycleNow,
  isOnline: () => typeof navigator === "undefined" || navigator.onLine,
  markViewed: markOfflineVideoViewed,
  list: listOfflineVideos,
  update: updateOfflineVideo,
  removeCache: deleteCachedVideo,
  getReserve: getLocalReserve,
  sync: syncViewedReels,
  confirmed: getConfirmedViewedReels,
  refreshSession: refreshManagementSession,
  reconcile: reconcileOfflineLibrary,
  schedule: (callback, milliseconds) => { window.setTimeout(callback, milliseconds); },
};

/** One browser-global, coalesced Stage 9 lifecycle. */
export class ViewedReelLifecycle {
  private readonly dependencies: Dependencies;
  private running: Promise<void> | null = null;
  private requested = false;
  private activeVideoId: string | null = null;
  private readonly listeners = new Set<() => void>();

  constructor(partial: Partial<Dependencies> = {}) { this.dependencies = { ...DEFAULT, ...partial }; }

  /** Lets the local-only feed refresh after durable lifecycle transitions. */
  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(): void {
    this.listeners.forEach((listener) => listener());
    // The download queue keeps an in-memory projection for the dashboard.
    // Lifecycle mutations happen outside that queue, so publish a local-only
    // signal after every durable mutation rather than leaving its count stale
    // until the next manual download or full reload.
    if (typeof window !== "undefined") window.dispatchEvent(new Event("offline-reels-library-changed"));
  }

  private async update(videoId: string, patch: Parameters<Dependencies["update"]>[1]): Promise<void> {
    await this.dependencies.update(videoId, patch);
    this.notify();
  }

  async recordViewed(videoId: string): Promise<boolean> {
    const record = await this.dependencies.markViewed(videoId, this.dependencies.now());
    if (!record) return false;
    if (!record.newlyRecorded) return false;
    this.notify();
    if (record.deleteAfter) {
      const delay = Math.max(0, Date.parse(record.deleteAfter) - Date.parse(this.dependencies.now()));
      this.dependencies.schedule(() => { void this.reconcile(); }, delay);
    }
    void this.reconcile();
    return true;
  }

  /** This protects a playing local object after its fixed deadline only. */
  setActiveVideoId(videoId: string | null): void {
    if (this.activeVideoId === videoId) return;
    this.activeVideoId = videoId;
    void this.reconcile();
  }

  reconcile(): Promise<void> {
    if (this.running) { this.requested = true; return this.running; }
    this.running = this.run().finally(() => {
      this.running = null;
      if (this.requested) { this.requested = false; void this.reconcile(); }
    });
    return this.running;
  }

  private async run(): Promise<void> {
    await this.syncOutbox();
    const now = Date.parse(this.dependencies.now());
    for (const record of await this.dependencies.list()) {
      if (!record.viewedAt || !record.deleteAfter || Date.parse(record.deleteAfter) > now || record.deletionState === "deleted") continue;
      if (record.id === this.activeVideoId) continue;
      await this.update(record.id, { deletionState: "deleting", lastViewReasonCode: null });
      try {
        // Cache Storage returns false when the object was already absent: this
        // is the intended crash-recovery no-op.
        await this.dependencies.removeCache(record.id);
        await this.update(record.id, {
          status: "deleted",
          cacheKey: null,
          downloadedBytes: 0,
          downloadedAt: null,
          deletionState: "deleted",
          lastViewReasonCode: null,
        });
      } catch {
        await this.update(record.id, { deletionState: "failed", lastViewReasonCode: "cache_delete_failed" });
      }
    }
    await this.dependencies.reconcile();
  }

  private async syncOutbox(): Promise<void> {
    if (!this.dependencies.isOnline()) return;
    // Re-pairing must not revive an account's server-confirmed Reel merely
    // because this installation has lost its media cache or was offline.
    try {
      const confirmed = new Set((await this.dependencies.confirmed()).confirmed_video_ids);
      for (const record of await this.dependencies.list()) {
        if (confirmed.has(record.id) && !record.viewedAt) {
          await this.dependencies.markViewed(record.id, this.dependencies.now());
          this.notify();
        }
      }
    } catch {
      // An unpaired or offline control plane cannot block a durable local view.
    }
    const settings = await this.dependencies.getReserve();
    const pending = (await this.dependencies.list()).filter((record) => record.viewSyncState === "pending" && (record.viewSyncAttempts ?? 0) < MAX_SYNC_ATTEMPTS).slice(0, MAX_SYNC_BATCH);
    if (!pending.length) return;
    try {
      // CSRF intentionally lives only in module memory. A cold PWA reload
      // must restore it from the HttpOnly management cookie before a durable
      // outbox can leave the device; an unpaired session leaves it pending.
      if (!await this.dependencies.refreshSession()) return;
      const result = await this.dependencies.sync({ device_uuid: settings.deviceId, events: pending.map((record) => ({ video_id: record.id })) });
      const confirmed = new Set(result.confirmed_video_ids);
      await Promise.all(pending.map((record) => this.update(record.id, confirmed.has(record.id)
        ? { viewSyncState: "synced" }
        : { viewSyncAttempts: Math.min(MAX_SYNC_ATTEMPTS, (record.viewSyncAttempts ?? 0) + 1) })));
    } catch {
      await Promise.all(pending.map((record) => this.update(record.id, {
        viewSyncAttempts: Math.min(MAX_SYNC_ATTEMPTS, (record.viewSyncAttempts ?? 0) + 1),
      })));
    }
  }
}

const GLOBAL_KEY = "__offlineReelsViewedLifecycleV1";
export function getViewedReelLifecycle(): ViewedReelLifecycle {
  if (typeof window === "undefined") throw new Error("ViewedReelLifecycle is browser-only.");
  const target = window as Window & { [GLOBAL_KEY]?: ViewedReelLifecycle };
  target[GLOBAL_KEY] ??= new ViewedReelLifecycle();
  return target[GLOBAL_KEY];
}

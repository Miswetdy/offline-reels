import { cancelCollectionRun, getCollectionRun, createCollectionRun, getInstagramStatus, getNormalizationStatus, ManagementApiError, reportReserve, getAccountCatalog } from "../api/management";
import type { Video } from "../api/videos";
import { getStorageEstimate } from "./storage";
import { getOfflineDownloadQueue, type OfflineDownloadQueue } from "./download-queue";
import { reconcileOfflineLibrary } from "./reconciliation";
import { getLocalReserve, setReserveCycleIntent, updateLocalReserve } from "./reserve-repository";
import type { LocalReserveRecord } from "./types";
import { AUTO_REFILL_ENABLED } from "./feature-flags";

export type ReserveState =
  | "idle" | "reconciling" | "evaluating" | "requesting_sources" | "waiting_for_collection"
  | "waiting_for_normalization" | "downloading" | "satisfied" | "offline" | "paused_by_user"
  | "quota_reached" | "cancelled" | "safe_error";

export type ReserveSnapshot = {
  state: ReserveState;
  settings: LocalReserveRecord | null;
  localCompletedCount: number;
  storagePercent: number | null;
};

// Retained Stage 8 request variant. The production-false feature gate rejects
// it before a cycle starts; keeping the type isolates the eventual re-enable.
type ReserveRequestIntent = "auto" | "manual" | "viewed_deletion";

type Dependencies = {
  queue: OfflineDownloadQueue;
  reconcile: typeof reconcileOfflineLibrary;
  getSettings: typeof getLocalReserve;
  setIntent: typeof setReserveCycleIntent;
  updateSettings: typeof updateLocalReserve;
  estimate: typeof getStorageEstimate;
  getCatalog: (options?: { signal?: AbortSignal }) => Promise<Video[]>;
  getStatus: typeof getInstagramStatus;
  startCollection: typeof createCollectionRun;
  cancelCollection: typeof cancelCollectionRun;
  getRun: typeof getCollectionRun;
  normalization: typeof getNormalizationStatus;
  report: typeof reportReserve;
  isOnline: () => boolean;
  isActive: () => boolean;
  wait: (milliseconds: number, signal: AbortSignal) => Promise<void>;
};

const DEFAULT: Dependencies = {
  queue: typeof window === "undefined" ? null as unknown as OfflineDownloadQueue : getOfflineDownloadQueue(),
  reconcile: reconcileOfflineLibrary,
  getSettings: getLocalReserve,
  setIntent: setReserveCycleIntent,
  updateSettings: updateLocalReserve,
  estimate: getStorageEstimate,
  getCatalog: async (options?: { signal?: AbortSignal }) => (await getAccountCatalog(options?.signal)).items,
  getStatus: getInstagramStatus,
  startCollection: createCollectionRun,
  cancelCollection: cancelCollectionRun,
  getRun: getCollectionRun,
  normalization: getNormalizationStatus,
  report: reportReserve,
  isOnline: () => typeof navigator === "undefined" || navigator.onLine,
  isActive: () => typeof document === "undefined" || document.visibilityState === "visible",
  wait: (milliseconds, signal) => new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, milliseconds);
    signal.addEventListener("abort", () => { window.clearTimeout(timer); reject(new DOMException("Cancelled", "AbortError")); }, { once: true });
  }),
};

const MAX_CYCLE_MS = 120_000;
const MAX_COLLECTION_REQUEST = 10;

function empty(): ReserveSnapshot {
  return { state: "idle", settings: null, localCompletedCount: 0, storagePercent: null };
}

function usableStoragePercent(usage: number | null, quota: number | null): number | null {
  if (usage === null || quota === null || quota <= 0) return null;
  return Math.min(100, Math.max(0, Math.ceil((usage / quota) * 100)));
}

/** One browser-global, bounded foreground reserve state machine. */
export class LocalReserveController {
  private readonly dependencies: Dependencies;
  private snapshot = empty();
  private readonly listeners = new Set<() => void>();
  private cycle: Promise<void> | null = null;
  private aborter: AbortController | null = null;
  private requestedWhileActive: ReserveRequestIntent | null = null;
  // Only a run created by this reserve cycle may be cancelled here. A queued
  // run from another management action remains owned by that action.
  private ownedCollectionRunId: string | null = null;

  constructor(partial: Partial<Dependencies> = {}) { this.dependencies = { ...DEFAULT, ...partial }; }
  getSnapshot = (): ReserveSnapshot => this.snapshot;
  subscribe(listener: () => void): () => void { this.listeners.add(listener); return () => this.listeners.delete(listener); }
  private set(state: ReserveState, patch: Partial<ReserveSnapshot> = {}): void { this.snapshot = { ...this.snapshot, state, ...patch }; this.listeners.forEach((listener) => listener()); }

  async updateSettings(patch: Parameters<typeof updateLocalReserve>[0]): Promise<void> {
    const settings = await this.dependencies.updateSettings(patch);
    this.set(this.snapshot.state, { settings });
    if (AUTO_REFILL_ENABLED && settings.autoRefillEnabled) void this.request("auto");
  }

  request(intent: ReserveRequestIntent = "auto"): Promise<void> {
    if (intent !== "manual" && !AUTO_REFILL_ENABLED) {
      this.set("idle", { settings: this.snapshot.settings === null ? null : { ...this.snapshot.settings, autoRefillEnabled: false } });
      return Promise.resolve();
    }
    if (this.cycle) {
      if (this.requestedWhileActive === null) this.requestedWhileActive = intent;
      return this.cycle;
    }
    this.cycle = this.run(intent).finally(() => {
      this.cycle = null;
      const requested = this.requestedWhileActive;
      this.requestedWhileActive = null;
      if (requested) void this.request(requested);
    });
    return this.cycle;
  }

  pause(): void { this.aborter?.abort(); this.set("paused_by_user"); }
  async cancel(): Promise<void> {
    this.aborter?.abort();
    const ownedRunId = this.ownedCollectionRunId;
    this.ownedCollectionRunId = null;
    if (ownedRunId) {
      // Cancellation is an idempotent same-origin management mutation. A
      // transient failure cannot resurrect local downloads, and the next
      // foreground reconciliation will observe the safe server state.
      await this.dependencies.cancelCollection(ownedRunId, crypto.randomUUID()).catch(() => undefined);
    }
    await this.dependencies.queue.cancelBatch();
    await this.dependencies.setIntent("none");
    this.set("cancelled");
  }

  private async run(intent: ReserveRequestIntent): Promise<void> {
    if (!this.dependencies.isOnline() || !this.dependencies.isActive()) { this.set("offline"); return; }
    const controller = new AbortController(); this.aborter = controller;
    const deadline = Date.now() + MAX_CYCLE_MS;
    try {
      let settings = await this.dependencies.getSettings();
      if (intent !== "manual" && (!AUTO_REFILL_ENABLED || !settings.autoRefillEnabled)) { this.set("idle", { settings }); return; }
      await this.dependencies.setIntent(intent === "manual" ? "manual" : "auto");
      // Queue snapshots are in-memory projections.  Restore its existing
      // IndexedDB-backed projection before deciding whether the local reserve
      // is below its target; otherwise a reload can see zero and create an
      // unnecessary collection run despite completed cached media.
      await (this.dependencies.queue as Partial<OfflineDownloadQueue>).initialize?.();
      this.set("reconciling", { settings });
      await this.dependencies.reconcile();
      // Stage 9 can update a viewed/deleted record outside the queue. Refresh
      // its projection before computing the reserve deficit, otherwise a
      // pre-deletion completed record can suppress the one coalesced refill.
      await (this.dependencies.queue as Partial<OfflineDownloadQueue>).refreshFromStorage?.();
      const queueSnapshot = this.dependencies.queue.getSnapshot();
      const estimate = await this.dependencies.estimate();
      const percent = usableStoragePercent(estimate.usage, estimate.quota);
      const completed = queueSnapshot.records.filter((item) => item.status === "completed" && !item.viewedAt).length;
      settings = await this.dependencies.updateSettings({ lastSuccessfulReconciliationAt: new Date().toISOString() });
      this.set("evaluating", { settings, localCompletedCount: completed, storagePercent: percent });
      if (percent !== null && percent >= settings.maxStoragePercent) { this.set("quota_reached"); return; }
      if (intent === "auto" && completed >= settings.lowWatermark) { this.set("satisfied"); await this.finish(settings, completed); return; }
      if (completed >= settings.desiredCount) { this.set("satisfied"); await this.finish(settings, completed); return; }

      let catalog = await this.dependencies.getCatalog({ signal: controller.signal });
      let candidates = await this.missing(catalog);
      if (candidates.length < settings.desiredCount - completed) {
        const status = await this.dependencies.getStatus(controller.signal);
        if (!status.active_collection) {
          this.set("requesting_sources");
          const deficit = Math.min(MAX_COLLECTION_REQUEST, settings.desiredCount - completed - candidates.length);
          const created = await this.dependencies.startCollection(Math.max(1, deficit), crypto.randomUUID());
          this.ownedCollectionRunId = created.collection_run.id;
          this.set("waiting_for_collection");
          await this.pollCollection(created.collection_run.id, deadline, controller.signal);
          this.ownedCollectionRunId = null;
          this.set("waiting_for_normalization");
          await this.pollNormalization(deadline, controller.signal);
        } else {
          this.set("waiting_for_collection");
          await this.pollActiveCollection(deadline, controller.signal);
          this.set("waiting_for_normalization");
          await this.pollNormalization(deadline, controller.signal);
        }
        catalog = await this.dependencies.getCatalog({ signal: controller.signal });
        candidates = await this.missing(catalog);
      }
      if (Date.now() >= deadline) { this.set("safe_error"); return; }
      this.set("downloading");
      await this.dependencies.queue.enqueueReserveAndStart(candidates, Math.max(0, settings.desiredCount - completed));
      const after = this.dependencies.queue.getSnapshot();
      const newCompleted = after.records.filter((item) => item.status === "completed" && !item.viewedAt).length;
      if (!this.dependencies.isOnline()) this.set("offline", { localCompletedCount: newCompleted });
      else if (after.currentErrorCode === "storage_quota_exceeded") this.set("quota_reached", { localCompletedCount: newCompleted });
      else if (newCompleted >= settings.desiredCount || candidates.length === 0) this.set("satisfied", { localCompletedCount: newCompleted });
      else this.set("safe_error", { localCompletedCount: newCompleted });
      await this.finish(settings, newCompleted);
    } catch (error) {
      if (controller.signal.aborted) {
        if (this.snapshot.state !== "paused_by_user" && this.snapshot.state !== "cancelled") this.set("cancelled");
      } else if (error instanceof ManagementApiError && error.code === "unpaired") this.set("safe_error");
      else this.set(this.dependencies.isOnline() ? "safe_error" : "offline");
    } finally { if (this.aborter === controller) this.aborter = null; }
  }

  private async missing(catalog: Video[]): Promise<Video[]> {
    const completed = new Set(this.dependencies.queue.getSnapshot().records.filter((item) => item.status === "completed" || Boolean(item.viewedAt) || item.deletionState === "deleted").map((item) => item.id));
    const unique = new Map(catalog.map((video) => [video.id, video]));
    return [...unique.values()].filter((video) => !completed.has(video.id));
  }
  private async pollCollection(id: string, deadline: number, signal: AbortSignal): Promise<void> {
    let delay = 500;
    while (Date.now() < deadline) {
      const run = (await this.dependencies.getRun(id, signal)).collection_run;
      if (run.status === "completed") return;
      if (run.status === "failed" || run.status === "cancelled") throw new Error("collection_terminal");
      await this.dependencies.wait(delay, signal); delay = Math.min(8_000, delay * 2);
    }
    throw new Error("collection_deadline");
  }
  private async pollActiveCollection(deadline: number, signal: AbortSignal): Promise<void> {
    let delay = 500;
    while (Date.now() < deadline) {
      if (!(await this.dependencies.getStatus(signal)).active_collection) return;
      await this.dependencies.wait(delay, signal); delay = Math.min(8_000, delay * 2);
    }
    throw new Error("collection_deadline");
  }
  private async pollNormalization(deadline: number, signal: AbortSignal): Promise<void> {
    let delay = 500;
    while (Date.now() < deadline) {
      const status = await this.dependencies.normalization(signal);
      if (status.pending === 0 && status.running === 0) return;
      await this.dependencies.wait(delay, signal); delay = Math.min(8_000, delay * 2);
    }
    throw new Error("normalization_deadline");
  }
  private async finish(settings: LocalReserveRecord, completed: number): Promise<void> {
    await this.dependencies.setIntent("none");
    if (!this.dependencies.isOnline()) return;
    await this.dependencies.report({
      device_uuid: settings.deviceId, auto_refill_enabled: settings.autoRefillEnabled,
      desired_count: settings.desiredCount, low_watermark: settings.lowWatermark,
      quota_threshold: settings.maxStoragePercent, local_completed_count: completed,
      reported_at: new Date().toISOString(),
    }).catch(() => undefined);
  }
}

const GLOBAL_KEY = "__offlineReelsReserveControllerV1";
export function getLocalReserveController(): LocalReserveController {
  if (typeof window === "undefined") throw new Error("LocalReserveController is browser-only.");
  const target = window as Window & { [GLOBAL_KEY]?: LocalReserveController };
  target[GLOBAL_KEY] ??= new LocalReserveController();
  return target[GLOBAL_KEY];
}

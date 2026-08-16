// @vitest-environment jsdom

import "fake-indexeddb/auto";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LocalReserveController } from "../../lib/offline/reserve-controller";
import { resetOfflineDatabase, VIDEO_ID_ONE, VIDEO_ID_TWO } from "./test-helpers";

const video = (id: string) => ({ id, title: "Reel", content_type: "video/mp4", byte_size: 4, created_at: "2026-08-12T00:00:00Z" });
const settings = { id: "primary" as const, deviceId: "11111111-1111-4111-8111-111111111111", autoRefillEnabled: true, desiredCount: 2, lowWatermark: 1, maxStoragePercent: 80, lastSuccessfulReconciliationAt: null, pendingCycle: "none" as const, updatedAt: "2026-08-12T00:00:00Z" };

beforeEach(async () => { await resetOfflineDatabase(); });

describe("Stage 8 local reserve controller", () => {
  it("keeps automatic reserve requests inactive in production", async () => {
    const queue = { getSnapshot: () => ({ records: [], currentErrorCode: null }), enqueueReserveAndStart: vi.fn().mockResolvedValue(2), cancelBatch: vi.fn() };
    const catalog = vi.fn().mockResolvedValue([video(VIDEO_ID_ONE), video(VIDEO_ID_TWO)]);
    const controller = new LocalReserveController({ queue: queue as never, reconcile: vi.fn(), getCatalog: catalog, getStatus: vi.fn(), startCollection: vi.fn(), getRun: vi.fn(), normalization: vi.fn(), getSettings: vi.fn().mockResolvedValue(settings), updateSettings: vi.fn().mockResolvedValue(settings), setIntent: vi.fn(), estimate: vi.fn().mockResolvedValue({ usage: 1, quota: 100 }), report: vi.fn(), isOnline: () => true, isActive: () => true });
    await Promise.all([controller.request("auto"), controller.request("auto")]);
    expect(catalog).not.toHaveBeenCalled();
    expect(queue.enqueueReserveAndStart).not.toHaveBeenCalled();
  });

  it("does not refill after a viewed deletion while the gate is disabled", async () => {
    const expandedSettings = { ...settings, desiredCount: 3, lowWatermark: 1 };
    const queue = {
      initialize: vi.fn(),
      getSnapshot: () => ({ records: [{ id: VIDEO_ID_ONE, status: "completed", viewedAt: null }], currentErrorCode: null }),
      enqueueReserveAndStart: vi.fn().mockResolvedValue(2),
      cancelBatch: vi.fn(),
    };
    const controller = new LocalReserveController({
      queue: queue as never, reconcile: vi.fn(),
      getCatalog: vi.fn().mockResolvedValue([video(VIDEO_ID_ONE), video(VIDEO_ID_TWO), video("video-three")]),
      getStatus: vi.fn(), startCollection: vi.fn(), getRun: vi.fn(), normalization: vi.fn(),
      getSettings: vi.fn().mockResolvedValue(expandedSettings), updateSettings: vi.fn().mockResolvedValue(expandedSettings),
      setIntent: vi.fn(), estimate: vi.fn().mockResolvedValue({ usage: 1, quota: 100 }), report: vi.fn(),
      isOnline: () => true, isActive: () => true,
    });

    await controller.request("viewed_deletion");

    expect(queue.enqueueReserveAndStart).not.toHaveBeenCalled();
  });

  it("does not refresh or collect for a viewed deletion while the gate is disabled", async () => {
    const expandedSettings = { ...settings, desiredCount: 3, lowWatermark: 1 };
    let records = [
      { id: VIDEO_ID_ONE, status: "completed", viewedAt: null as string | null },
      { id: VIDEO_ID_TWO, status: "completed", viewedAt: null as string | null },
      { id: "viewed-video", status: "completed", viewedAt: null as string | null },
    ];
    const refreshFromStorage = vi.fn(async () => {
      records = [
        { id: VIDEO_ID_ONE, status: "completed", viewedAt: null },
        { id: VIDEO_ID_TWO, status: "completed", viewedAt: null },
        { id: "viewed-video", status: "deleted", viewedAt: "2026-08-13T12:00:00.000Z" },
      ];
    });
    const queue = {
      initialize: vi.fn(), refreshFromStorage,
      getSnapshot: () => ({ records, currentErrorCode: null }),
      enqueueReserveAndStart: vi.fn().mockResolvedValue(1), cancelBatch: vi.fn(),
    };
    const controller = new LocalReserveController({
      queue: queue as never, reconcile: vi.fn(),
      getCatalog: vi.fn().mockResolvedValue([video(VIDEO_ID_ONE), video(VIDEO_ID_TWO), video("replacement-video")]),
      getStatus: vi.fn(), startCollection: vi.fn(), getRun: vi.fn(), normalization: vi.fn(),
      getSettings: vi.fn().mockResolvedValue(expandedSettings), updateSettings: vi.fn().mockResolvedValue(expandedSettings),
      setIntent: vi.fn(), estimate: vi.fn().mockResolvedValue({ usage: 1, quota: 100 }), report: vi.fn(),
      isOnline: () => true, isActive: () => true,
    });

    await controller.request("viewed_deletion");

    expect(refreshFromStorage).not.toHaveBeenCalled();
    expect(queue.enqueueReserveAndStart).not.toHaveBeenCalled();
  });

  it("manual download still reports offline safely", async () => {
    const controller = new LocalReserveController({ isOnline: () => false });
    await controller.request("manual");
    expect(controller.getSnapshot().state).toBe("offline");
  });

  it("cancellation leaves completed records to the existing queue", async () => {
    const cancelBatch = vi.fn();
    const controller = new LocalReserveController({ queue: { cancelBatch } as never, setIntent: vi.fn() });
    await controller.cancel();
    expect(cancelBatch).toHaveBeenCalledOnce();
    expect(controller.getSnapshot().state).toBe("cancelled");
  });

  it("cancels only the collection run created by the active reserve cycle", async () => {
    const cancelCollection = vi.fn().mockResolvedValue(undefined);
    const queue = { initialize: vi.fn(), getSnapshot: () => ({ records: [], currentErrorCode: null }), enqueueReserveAndStart: vi.fn(), cancelBatch: vi.fn() };
    const controller = new LocalReserveController({
      queue: queue as never,
      reconcile: vi.fn(),
      getSettings: vi.fn().mockResolvedValue(settings), updateSettings: vi.fn().mockResolvedValue(settings), setIntent: vi.fn(),
      estimate: vi.fn().mockResolvedValue({ usage: 0, quota: 100 }), getCatalog: vi.fn().mockResolvedValue([]),
      getStatus: vi.fn().mockResolvedValue({ active_collection: null }),
      startCollection: vi.fn().mockResolvedValue({ collection_run: { id: "reserve-owned-run" } }),
      cancelCollection,
      getRun: vi.fn().mockResolvedValue({ collection_run: { status: "queued" } }), normalization: vi.fn(), report: vi.fn(),
      isOnline: () => true, isActive: () => true,
      wait: (_milliseconds, signal) => new Promise<void>((_resolve, reject) => signal.addEventListener("abort", () => reject(new DOMException("Cancelled", "AbortError")), { once: true })),
    });
    const cycle = controller.request("manual");
    await vi.waitFor(() => expect(controller.getSnapshot().state).toBe("waiting_for_collection"));
    await controller.cancel();
    await cycle;
    expect(cancelCollection).toHaveBeenCalledWith("reserve-owned-run", expect.any(String));
    expect(queue.cancelBatch).toHaveBeenCalledOnce();
    expect(controller.getSnapshot().state).toBe("cancelled");
  });
});

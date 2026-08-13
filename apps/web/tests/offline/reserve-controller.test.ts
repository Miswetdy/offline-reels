// @vitest-environment jsdom

import "fake-indexeddb/auto";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LocalReserveController } from "../../lib/offline/reserve-controller";
import { resetOfflineDatabase, VIDEO_ID_ONE, VIDEO_ID_TWO } from "./test-helpers";

const video = (id: string) => ({ id, title: "Reel", content_type: "video/mp4", byte_size: 4, created_at: "2026-08-12T00:00:00Z" });
const settings = { id: "primary" as const, deviceId: "11111111-1111-4111-8111-111111111111", autoRefillEnabled: true, desiredCount: 2, lowWatermark: 1, maxStoragePercent: 80, lastSuccessfulReconciliationAt: null, pendingCycle: "none" as const, updatedAt: "2026-08-12T00:00:00Z" };

beforeEach(async () => { await resetOfflineDatabase(); });

describe("Stage 8 local reserve controller", () => {
  it("coalesces starts and skips collection when catalog is sufficient", async () => {
    const queue = { getSnapshot: () => ({ records: [], currentErrorCode: null }), enqueueReserveAndStart: vi.fn().mockResolvedValue(2), cancelBatch: vi.fn() };
    const catalog = vi.fn().mockResolvedValue([video(VIDEO_ID_ONE), video(VIDEO_ID_TWO)]);
    const controller = new LocalReserveController({ queue: queue as never, reconcile: vi.fn(), getCatalog: catalog, getStatus: vi.fn(), startCollection: vi.fn(), getRun: vi.fn(), normalization: vi.fn(), getSettings: vi.fn().mockResolvedValue(settings), updateSettings: vi.fn().mockResolvedValue(settings), setIntent: vi.fn(), estimate: vi.fn().mockResolvedValue({ usage: 1, quota: 100 }), report: vi.fn(), isOnline: () => true, isActive: () => true });
    await Promise.all([controller.request("auto"), controller.request("auto")]);
    expect(catalog).toHaveBeenCalledTimes(1);
    expect(queue.enqueueReserveAndStart).toHaveBeenCalledWith(expect.any(Array), 2);
  });

  it("pauses safely offline", async () => {
    const controller = new LocalReserveController({ isOnline: () => false });
    await controller.request("auto");
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

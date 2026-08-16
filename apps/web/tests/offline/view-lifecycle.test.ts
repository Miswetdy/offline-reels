// @vitest-environment jsdom

import { describe, expect, it, vi } from "vitest";

import { ViewedReelLifecycle } from "../../lib/offline/view-lifecycle";
import type { OfflineVideoRecord } from "../../lib/offline/types";
import { VIDEO_ID_ONE } from "./test-helpers";

const viewedAt = "2026-08-13T10:00:00.000Z";
const beforeDeadline = "2026-08-13T10:59:59.999Z";
const afterDeadline = "2026-08-13T11:00:00.000Z";

function record(overrides: Partial<OfflineVideoRecord> = {}): OfflineVideoRecord {
  return {
    id: VIDEO_ID_ONE, title: "Reel", contentType: "video/mp4", byteSize: 10,
    createdAt: viewedAt, status: "completed", downloadedBytes: 10, downloadedAt: viewedAt,
    cacheKey: `/offline-media/${VIDEO_ID_ONE}`, lastErrorCode: null, lastErrorMessage: null,
    failedAt: null, lastWatchedAt: null, viewedAt, deleteAfter: "2026-08-13T11:00:00.000Z",
    deletionState: "pending", viewSyncState: "pending", viewSyncAttempts: 0,
    lastViewReasonCode: null, updatedAt: viewedAt, ...overrides,
  };
}

function harness(overrides: Record<string, unknown> = {}) {
  const clock = { now: afterDeadline };
  const records = new Map([[VIDEO_ID_ONE, record()]]);
  const update = vi.fn(async (id: string, patch: object) => {
    const previous = records.get(id);
    if (!previous) return undefined;
    const next = { ...previous, ...patch } as OfflineVideoRecord;
    records.set(id, next);
    return next;
  });
  const markViewed = vi.fn(async (id: string, at: string) => {
    const previous = records.get(id);
    if (!previous) return undefined;
    if (previous.viewedAt) return { ...previous, newlyRecorded: false };
    const next = { ...previous, viewedAt: at, deleteAfter: new Date(Date.parse(at) + 3_600_000).toISOString(), deletionState: "pending" as const, viewSyncState: "pending" as const };
    records.set(id, next);
    return { ...next, newlyRecorded: true };
  });
  const dependencies = {
    now: () => clock.now,
    isOnline: () => true,
    list: vi.fn(async () => [...records.values()]),
    update,
    markViewed,
    removeCache: vi.fn(async () => true),
    getReserve: vi.fn(async () => ({ deviceId: "11111111-1111-4111-8111-111111111111", autoRefillEnabled: true })),
    sync: vi.fn(async () => ({ confirmed_video_ids: [VIDEO_ID_ONE] })),
    confirmed: vi.fn(async () => ({ confirmed_video_ids: [] })),
    refreshSession: vi.fn(async () => true),
    reconcile: vi.fn(async () => ({})),
    refill: vi.fn(async () => undefined),
    schedule: vi.fn(),
    ...overrides,
  };
  return { records, dependencies, clock, lifecycle: new ViewedReelLifecycle(dependencies as never) };
}

describe("Stage 9 viewed Reel lifecycle", () => {
  it("keeps an offline durable outbox and collapses duplicate local events", async () => {
    const item = harness({ isOnline: () => false });
    item.records.set(VIDEO_ID_ONE, record({ viewedAt: undefined, deleteAfter: undefined, deletionState: "none", viewSyncState: "none" }));
    await expect(item.lifecycle.recordViewed(VIDEO_ID_ONE)).resolves.toBe(true);
    await expect(item.lifecycle.recordViewed(VIDEO_ID_ONE)).resolves.toBe(false);
    expect(item.records.get(VIDEO_ID_ONE)).toMatchObject({ viewSyncState: "pending", viewSyncAttempts: 0 });
    expect(item.dependencies.sync).not.toHaveBeenCalled();
  });

  it("preserves the first viewedAt and deleteAfter across later swipe attempts", async () => {
    const item = harness({ isOnline: () => false });
    item.records.set(VIDEO_ID_ONE, record({ viewedAt: undefined, deleteAfter: undefined, deletionState: "none", viewSyncState: "none" }));
    item.clock.now = viewedAt;
    await item.lifecycle.recordViewed(VIDEO_ID_ONE);
    item.clock.now = "2026-08-13T10:30:00.000Z";
    await item.lifecycle.recordViewed(VIDEO_ID_ONE);
    expect(item.records.get(VIDEO_ID_ONE)).toMatchObject({ viewedAt, deleteAfter: "2026-08-13T11:00:00.000Z" });
  });

  it("defers an overdue cache deletion only while that Reel is active", async () => {
    const item = harness();
    item.lifecycle.setActiveVideoId(VIDEO_ID_ONE);
    await item.lifecycle.reconcile();
    expect(item.dependencies.removeCache).not.toHaveBeenCalled();
    item.lifecycle.setActiveVideoId(null);
    await item.lifecycle.reconcile();
    expect(item.dependencies.removeCache).toHaveBeenCalledOnce();
    expect(item.records.get(VIDEO_ID_ONE)).toMatchObject({ deletionState: "deleted", deleteAfter: "2026-08-13T11:00:00.000Z" });
  });

  it("does not delete before one hour, then deletes only the local object", async () => {
    const item = harness();
    item.clock.now = beforeDeadline;
    await item.lifecycle.reconcile();
    expect(item.dependencies.removeCache).not.toHaveBeenCalled();
    item.clock.now = afterDeadline;
    await item.lifecycle.reconcile();
    expect(item.records.get(VIDEO_ID_ONE)).toMatchObject({ status: "deleted", deletionState: "deleted", cacheKey: null });
    expect(item.dependencies.refill).not.toHaveBeenCalled();
    await item.lifecycle.reconcile();
    expect(item.dependencies.removeCache).toHaveBeenCalledTimes(1);
    expect(item.dependencies.refill).not.toHaveBeenCalled();
  });

  it("never starts auto-refill after a cold wake", async () => {
    const refreshSession = vi.fn(async () => true);
    const item = harness({ refreshSession });

    await item.lifecycle.reconcile();

    expect(refreshSession).toHaveBeenCalled();
    expect(item.dependencies.refill).not.toHaveBeenCalled();
  });

  it("keeps the deletion tombstone when an unpaired cold wake cannot refill", async () => {
    const item = harness({ refreshSession: vi.fn(async () => false) });

    await item.lifecycle.reconcile();

    expect(item.records.get(VIDEO_ID_ONE)).toMatchObject({ status: "deleted", deletionState: "deleted", viewedAt });
    expect(item.dependencies.refill).not.toHaveBeenCalled();
  });

  it("treats an already absent Cache object as successful deletion", async () => {
    const item = harness({ removeCache: vi.fn(async () => false) });
    await item.lifecycle.reconcile();
    expect(item.records.get(VIDEO_ID_ONE)).toMatchObject({ deletionState: "deleted", status: "deleted" });
  });

  it("retains the tombstone after delete failure and retries it on the next wake", async () => {
    const removeCache = vi.fn().mockRejectedValueOnce(new Error("cache failed")).mockResolvedValueOnce(true);
    const item = harness({ removeCache });
    await item.lifecycle.reconcile();
    expect(item.records.get(VIDEO_ID_ONE)).toMatchObject({ deletionState: "failed", viewedAt });
    await item.lifecycle.reconcile();
    expect(removeCache).toHaveBeenCalledTimes(2);
    expect(item.records.get(VIDEO_ID_ONE)).toMatchObject({ deletionState: "deleted" });
  });

  it("keeps an offline-sync outbox durable and bounds retry attempts", async () => {
    const sync = vi.fn().mockRejectedValue(new Error("offline"));
    const item = harness({ sync });
    item.records.set(VIDEO_ID_ONE, record({ deleteAfter: "2026-08-13T12:00:00.000Z" }));
    for (let attempt = 0; attempt < 6; attempt += 1) await item.lifecycle.reconcile();
    expect(sync).toHaveBeenCalledTimes(5);
    expect(item.records.get(VIDEO_ID_ONE)).toMatchObject({
      viewedAt, viewSyncState: "pending", viewSyncAttempts: 5,
    });
  });

  it("restores the in-memory CSRF session after reload before syncing the durable outbox", async () => {
    const refreshSession = vi.fn(async () => true);
    const item = harness({ refreshSession });
    item.records.set(VIDEO_ID_ONE, record({ deleteAfter: "2026-08-13T12:00:00.000Z" }));
    await item.lifecycle.reconcile();
    expect(refreshSession).toHaveBeenCalledTimes(1);
    expect(item.dependencies.sync).toHaveBeenCalledTimes(1);
    expect(item.records.get(VIDEO_ID_ONE)).toMatchObject({ viewSyncState: "synced" });
  });

  it("keeps the outbox pending when a reloaded PWA is no longer paired", async () => {
    const item = harness({ refreshSession: vi.fn(async () => false) });
    item.records.set(VIDEO_ID_ONE, record({ deleteAfter: "2026-08-13T12:00:00.000Z" }));
    await item.lifecycle.reconcile();
    expect(item.dependencies.sync).not.toHaveBeenCalled();
    expect(item.records.get(VIDEO_ID_ONE)).toMatchObject({ viewSyncState: "pending", viewSyncAttempts: 0 });
  });

  it("reconciles server-confirmed IDs after re-pair without clearing local tombstones", async () => {
    const item = harness({ confirmed: vi.fn(async () => ({ confirmed_video_ids: [VIDEO_ID_ONE] })) });
    item.records.set(VIDEO_ID_ONE, record({ viewedAt: undefined, deleteAfter: undefined, deletionState: "none", viewSyncState: "none" }));
    await item.lifecycle.reconcile();
    expect(item.dependencies.markViewed).toHaveBeenCalledWith(VIDEO_ID_ONE, afterDeadline);
    expect(item.records.get(VIDEO_ID_ONE)).toMatchObject({ viewedAt: afterDeadline, viewSyncState: "synced" });
  });

  it("coalesces simultaneous wakes into one local deletion", async () => {
    let release: (() => void) | undefined;
    const wait = new Promise<void>((resolve) => { release = resolve; });
    const item = harness({ removeCache: vi.fn(async () => { await wait; return true; }) });
    const first = item.lifecycle.reconcile();
    const second = item.lifecycle.reconcile();
    release?.();
    await Promise.all([first, second]);
    expect(item.dependencies.removeCache).toHaveBeenCalledTimes(1);
    expect(item.dependencies.refill).not.toHaveBeenCalled();
  });

  it("notifies the local feed when durable deletion state changes", async () => {
    const item = harness();
    const states: Array<OfflineVideoRecord["deletionState"]> = [];
    const unsubscribe = item.lifecycle.subscribe(() => states.push(item.records.get(VIDEO_ID_ONE)?.deletionState));

    await item.lifecycle.reconcile();
    unsubscribe();

    expect(states).toEqual(expect.arrayContaining(["deleting", "deleted"]));
  });

  it("publishes lifecycle changes so the dashboard can refresh its queue projection", async () => {
    const item = harness();
    const changed = vi.fn();
    window.addEventListener("offline-reels-library-changed", changed);

    await item.lifecycle.reconcile();

    window.removeEventListener("offline-reels-library-changed", changed);
    expect(changed).toHaveBeenCalled();
  });
});

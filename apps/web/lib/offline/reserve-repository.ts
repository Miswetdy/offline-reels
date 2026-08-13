import { LOCAL_RESERVE_ID, type LocalReserveRecord, type ReserveCycleIntent } from "./types";
import { LOCAL_RESERVE_STORE, withOfflineDatabase } from "./db";

export const DEFAULT_DESIRED_RESERVE = 20;
export const DEFAULT_LOW_WATERMARK = 8;
export const DEFAULT_MAX_STORAGE_PERCENT = 80;

function newDeviceId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  throw new Error("A stable device identifier cannot be created in this browser.");
}

function now(): string {
  return new Date().toISOString();
}

function defaults(): LocalReserveRecord {
  return {
    id: LOCAL_RESERVE_ID,
    deviceId: newDeviceId(),
    autoRefillEnabled: false,
    desiredCount: DEFAULT_DESIRED_RESERVE,
    lowWatermark: DEFAULT_LOW_WATERMARK,
    maxStoragePercent: DEFAULT_MAX_STORAGE_PERCENT,
    lastSuccessfulReconciliationAt: null,
    pendingCycle: "none",
    updatedAt: now(),
  };
}

function assertRecord(record: LocalReserveRecord): void {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(record.deviceId)) {
    throw new TypeError("Invalid local device identifier.");
  }
  if (!Number.isInteger(record.desiredCount) || record.desiredCount < 1 || record.desiredCount > 100) throw new TypeError("Invalid desired reserve.");
  if (!Number.isInteger(record.lowWatermark) || record.lowWatermark < 0 || record.lowWatermark >= record.desiredCount) throw new TypeError("Invalid local reserve watermark.");
  if (!Number.isInteger(record.maxStoragePercent) || record.maxStoragePercent < 50 || record.maxStoragePercent > 95) throw new TypeError("Invalid storage threshold.");
}

export async function getLocalReserve(): Promise<LocalReserveRecord> {
  return withOfflineDatabase(async (database) => {
    const existing = await database.get(LOCAL_RESERVE_STORE, LOCAL_RESERVE_ID);
    if (existing) return existing;
    const created = defaults();
    await database.put(LOCAL_RESERVE_STORE, created);
    return created;
  });
}

export async function updateLocalReserve(
  patch: Partial<Omit<LocalReserveRecord, "id" | "deviceId" | "updatedAt">>,
): Promise<LocalReserveRecord> {
  return withOfflineDatabase(async (database) => {
    const current = await database.get(LOCAL_RESERVE_STORE, LOCAL_RESERVE_ID) ?? defaults();
    const next: LocalReserveRecord = { ...current, ...patch, updatedAt: now() };
    assertRecord(next);
    await database.put(LOCAL_RESERVE_STORE, next);
    return next;
  });
}

export async function setReserveCycleIntent(intent: ReserveCycleIntent): Promise<LocalReserveRecord> {
  return updateLocalReserve({ pendingCycle: intent });
}

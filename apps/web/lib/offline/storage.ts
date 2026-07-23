export const STORAGE_SAFETY_MULTIPLIER = 1.2;
export const MINIMUM_STORAGE_RESERVE_BYTES = 50 * 1024 * 1024;

export type LocalStorageEstimate = {
  usage: number | null;
  quota: number | null;
  available: number | null;
  isAvailable: boolean;
};

export type PersistentStorageResult = "granted" | "denied" | "unavailable";

function getStorageManager(): StorageManager | undefined {
  if (typeof navigator === "undefined") return undefined;
  return navigator.storage;
}

export async function getStorageEstimate(): Promise<LocalStorageEstimate> {
  const storage = getStorageManager();
  if (!storage?.estimate) {
    return { usage: null, quota: null, available: null, isAvailable: false };
  }

  try {
    const estimate = await storage.estimate();
    const usage = typeof estimate.usage === "number" ? estimate.usage : null;
    const quota = typeof estimate.quota === "number" ? estimate.quota : null;
    return {
      usage,
      quota,
      available: usage !== null && quota !== null ? Math.max(0, quota - usage) : null,
      isAvailable: true,
    };
  } catch {
    return { usage: null, quota: null, available: null, isAvailable: false };
  }
}

export async function requestPersistentStorage(): Promise<PersistentStorageResult> {
  const storage = getStorageManager();
  if (!storage?.persist) return "unavailable";

  try {
    return (await storage.persist()) ? "granted" : "denied";
  } catch {
    return "denied";
  }
}

/**
 * Reports the browser's current persistent-storage decision without requesting
 * it. `null` means that the browser does not expose the API or rejected the
 * diagnostic call.
 */
export async function getPersistentStorageStatus(): Promise<boolean | null> {
  const storage = getStorageManager();
  if (!storage?.persisted) return null;

  try {
    return await storage.persisted();
  } catch {
    return null;
  }
}

export function calculateExpectedRequiredSpace(downloadBytes: number): number {
  if (!Number.isSafeInteger(downloadBytes) || downloadBytes <= 0) {
    throw new TypeError("downloadBytes must be a positive integer.");
  }
  return Math.ceil(downloadBytes * STORAGE_SAFETY_MULTIPLIER) + MINIMUM_STORAGE_RESERVE_BYTES;
}

export function hasEstimatedSpaceForDownload(downloadBytes: number, estimate: LocalStorageEstimate): boolean {
  if (estimate.available === null) return true;
  return estimate.available >= calculateExpectedRequiredSpace(downloadBytes);
}

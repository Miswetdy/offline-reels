import { afterEach, describe, expect, it, vi } from "vitest";

import {
  MINIMUM_STORAGE_RESERVE_BYTES,
  STORAGE_SAFETY_MULTIPLIER,
  calculateExpectedRequiredSpace,
  getStorageEstimate,
  hasEstimatedSpaceForDownload,
  requestPersistentStorage,
} from "../../lib/offline/storage";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("browser storage helpers", () => {
  it("returns a storage estimate when the API is available", async () => {
    vi.stubGlobal("navigator", { storage: { estimate: vi.fn().mockResolvedValue({ usage: 100, quota: 1000 }) } });
    await expect(getStorageEstimate()).resolves.toEqual({ usage: 100, quota: 1000, available: 900, isAvailable: true });
  });

  it("does not hard-block when the estimate API is unavailable", async () => {
    vi.stubGlobal("navigator", {});
    const estimate = await getStorageEstimate();
    expect(estimate.isAvailable).toBe(false);
    expect(hasEstimatedSpaceForDownload(100, estimate)).toBe(true);
  });

  it("reports persistent-storage acceptance, rejection and absence without throwing", async () => {
    vi.stubGlobal("navigator", { storage: { persist: vi.fn().mockResolvedValue(true) } });
    await expect(requestPersistentStorage()).resolves.toBe("granted");
    vi.stubGlobal("navigator", { storage: { persist: vi.fn().mockResolvedValue(false) } });
    await expect(requestPersistentStorage()).resolves.toBe("denied");
    vi.stubGlobal("navigator", {});
    await expect(requestPersistentStorage()).resolves.toBe("unavailable");
  });

  it("uses the safety multiplier and 50 MiB reserve when deciding on available space", () => {
    const downloadBytes = 100;
    expect(calculateExpectedRequiredSpace(downloadBytes)).toBe(
      Math.ceil(downloadBytes * STORAGE_SAFETY_MULTIPLIER) + MINIMUM_STORAGE_RESERVE_BYTES,
    );
    expect(
      hasEstimatedSpaceForDownload(downloadBytes, {
        usage: 0,
        quota: calculateExpectedRequiredSpace(downloadBytes),
        available: calculateExpectedRequiredSpace(downloadBytes),
        isAvailable: true,
      }),
    ).toBe(true);
    expect(
      hasEstimatedSpaceForDownload(downloadBytes, {
        usage: 0,
        quota: calculateExpectedRequiredSpace(downloadBytes) - 1,
        available: calculateExpectedRequiredSpace(downloadBytes) - 1,
        isAvailable: true,
      }),
    ).toBe(false);
  });
});

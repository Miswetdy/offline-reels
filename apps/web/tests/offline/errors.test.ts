import { describe, expect, it } from "vitest";

import { getOfflineErrorMessage, toOfflineStorageError } from "../../lib/offline/errors";

describe("offline storage errors", () => {
  it("maps quota, abort and unavailable browser errors to safe typed codes", () => {
    expect(toOfflineStorageError(new DOMException("quota", "QuotaExceededError")).code).toBe("storage_quota_exceeded");
    expect(toOfflineStorageError(new DOMException("abort", "AbortError")).code).toBe("download_aborted");
    expect(toOfflineStorageError(new DOMException("blocked", "SecurityError")).code).toBe("browser_storage_unavailable");
  });

  it("does not use a raw internal cause as the user-facing error message", () => {
    const error = toOfflineStorageError(new Error("internal storage detail"));
    expect(error.userMessage).toBe(getOfflineErrorMessage("unknown_error"));
    expect(error.userMessage).not.toContain("internal storage detail");
  });
});

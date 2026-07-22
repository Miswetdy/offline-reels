import type { OfflineErrorCode } from "./types";

const USER_MESSAGES: Record<OfflineErrorCode, string> = {
  network_error: "The video could not be downloaded because the network is unavailable.",
  http_error: "The video server returned an unexpected response.",
  response_body_missing: "The video response did not contain media data.",
  unsupported_content_type: "This video format is not supported for offline storage.",
  content_length_mismatch: "The downloaded video size does not match the expected size.",
  byte_size_mismatch: "The downloaded video size does not match the expected size.",
  cache_write_failed: "The video could not be saved to local storage.",
  cache_validation_failed: "The local video file could not be validated.",
  storage_quota_exceeded: "There is not enough browser storage available for this video.",
  download_aborted: "The video download was cancelled.",
  download_interrupted: "The video download was interrupted before it finished.",
  cache_entry_missing: "The local video file is no longer available.",
  browser_storage_unavailable: "Browser storage is unavailable in this environment.",
  invalid_video_id: "The local video identifier is invalid.",
  unknown_error: "The local video library could not be updated.",
};

export class OfflineStorageError extends Error {
  readonly code: OfflineErrorCode;
  readonly userMessage: string;

  constructor(code: OfflineErrorCode, cause?: unknown) {
    super(USER_MESSAGES[code], cause === undefined ? undefined : { cause });
    this.name = "OfflineStorageError";
    this.code = code;
    this.userMessage = USER_MESSAGES[code];
  }
}

export function isOfflineStorageError(error: unknown): error is OfflineStorageError {
  return error instanceof OfflineStorageError;
}

export function toOfflineStorageError(
  error: unknown,
  fallbackCode: OfflineErrorCode = "unknown_error",
): OfflineStorageError {
  if (isOfflineStorageError(error)) return error;

  if (error instanceof DOMException) {
    if (error.name === "QuotaExceededError") return new OfflineStorageError("storage_quota_exceeded", error);
    if (error.name === "AbortError") return new OfflineStorageError("download_aborted", error);
    if (error.name === "SecurityError" || error.name === "InvalidStateError") {
      return new OfflineStorageError("browser_storage_unavailable", error);
    }
  }

  return new OfflineStorageError(fallbackCode, error);
}

export function getOfflineErrorMessage(code: OfflineErrorCode): string {
  return USER_MESSAGES[code];
}

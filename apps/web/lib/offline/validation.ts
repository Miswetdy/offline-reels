import { OfflineStorageError } from "./errors";
import { getOfflineMediaPath, normalizeVideoId } from "./media-key";
import { OFFLINE_ERROR_CODES, OFFLINE_VIDEO_STATUSES, type OfflineVideoRecord } from "./types";

export function isAllowedVideoContentType(contentType: string): boolean {
  return contentType.split(";", 1)[0]?.trim().toLowerCase() === "video/mp4";
}

function isIsoDate(value: string | null): value is string {
  return value !== null && Number.isFinite(Date.parse(value));
}

function assertNullableIsoDate(value: string | null, field: string): void {
  if (value !== null && !isIsoDate(value)) {
    throw new OfflineStorageError("unknown_error", new Error(`${field} must be an ISO date.`));
  }
}

export function assertOfflineVideoRecord(record: OfflineVideoRecord): void {
  normalizeVideoId(record.id);

  if (record.title.trim().length === 0 || record.title.length > 255) {
    throw new OfflineStorageError("unknown_error", new Error("title is invalid."));
  }

  if (!isAllowedVideoContentType(record.contentType)) {
    throw new OfflineStorageError("unsupported_content_type");
  }

  if (!Number.isSafeInteger(record.byteSize) || record.byteSize <= 0) {
    throw new OfflineStorageError("byte_size_mismatch");
  }

  if (!OFFLINE_VIDEO_STATUSES.includes(record.status)) {
    throw new OfflineStorageError("unknown_error", new Error("status is invalid."));
  }

  if (!Number.isSafeInteger(record.downloadedBytes) || record.downloadedBytes < 0) {
    throw new OfflineStorageError("byte_size_mismatch");
  }

  if (!isIsoDate(record.createdAt) || !isIsoDate(record.updatedAt)) {
    throw new OfflineStorageError("unknown_error", new Error("record dates are invalid."));
  }

  assertNullableIsoDate(record.downloadedAt, "downloadedAt");
  assertNullableIsoDate(record.failedAt, "failedAt");
  assertNullableIsoDate(record.lastWatchedAt, "lastWatchedAt");

  if (record.cacheKey !== null && record.cacheKey !== getOfflineMediaPath(record.id)) {
    throw new OfflineStorageError("invalid_video_id");
  }

  if (record.lastErrorCode !== null && !OFFLINE_ERROR_CODES.includes(record.lastErrorCode)) {
    throw new OfflineStorageError("unknown_error", new Error("lastErrorCode is invalid."));
  }

  if (record.lastErrorMessage !== null && record.lastErrorMessage.length > 500) {
    throw new OfflineStorageError("unknown_error", new Error("lastErrorMessage is too long."));
  }

  if (record.status === "completed") {
    if (record.cacheKey === null || record.downloadedAt === null || record.downloadedBytes !== record.byteSize) {
      throw new OfflineStorageError("cache_validation_failed");
    }
  }
}

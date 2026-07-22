export const OFFLINE_VIDEO_STATUSES = ["queued", "downloading", "completed", "failed"] as const;

export type OfflineVideoStatus = (typeof OFFLINE_VIDEO_STATUSES)[number];

export const OFFLINE_ERROR_CODES = [
  "network_error",
  "http_error",
  "response_body_missing",
  "unsupported_content_type",
  "content_length_mismatch",
  "byte_size_mismatch",
  "cache_write_failed",
  "cache_validation_failed",
  "storage_quota_exceeded",
  "download_aborted",
  "download_interrupted",
  "cache_entry_missing",
  "browser_storage_unavailable",
  "invalid_video_id",
  "unknown_error",
] as const;

export type OfflineErrorCode = (typeof OFFLINE_ERROR_CODES)[number];

export type OfflineVideoRecord = {
  id: string;
  title: string;
  contentType: string;
  byteSize: number;
  createdAt: string;
  status: OfflineVideoStatus;
  downloadedBytes: number;
  downloadedAt: string | null;
  cacheKey: string | null;
  lastErrorCode: OfflineErrorCode | null;
  lastErrorMessage: string | null;
  failedAt: string | null;
  lastWatchedAt: string | null;
  updatedAt: string;
};

export type OfflineVideoPatch = Partial<Omit<OfflineVideoRecord, "id" | "updatedAt">>;

export type CachedVideoMetadata = Pick<OfflineVideoRecord, "cacheKey" | "contentType" | "byteSize">;

export type CachedVideoValidation =
  | { valid: true; byteSize: number }
  | {
      valid: false;
      reason: "missing" | "cache_key_mismatch" | "invalid_content_type" | "size_mismatch";
    };

import { OfflineStorageError, toOfflineStorageError } from "./errors";
import { getCachedVideo } from "./media-cache";
import { normalizeVideoId } from "./media-key";
import { isAllowedVideoContentType } from "./validation";

export type OfflinePlaybackSource = {
  url: string;
  revoke: () => void;
};

export async function createOfflinePlaybackSource(videoId: string): Promise<OfflinePlaybackSource> {
  try {
    normalizeVideoId(videoId);
    const response = await getCachedVideo(videoId);
    if (!response) throw new OfflineStorageError("cache_entry_missing");
    if (response.body === null) throw new OfflineStorageError("response_body_missing");
    if (!isAllowedVideoContentType(response.headers.get("content-type") ?? "")) {
      throw new OfflineStorageError("unsupported_content_type");
    }
    if (typeof URL.createObjectURL !== "function" || typeof URL.revokeObjectURL !== "function") {
      throw new OfflineStorageError("browser_storage_unavailable");
    }

    const blob = await response.blob();
    if (blob.size === 0) throw new OfflineStorageError("cache_validation_failed");
    const url = URL.createObjectURL(blob);
    let revoked = false;
    return {
      url,
      revoke: () => {
        if (revoked) return;
        revoked = true;
        URL.revokeObjectURL(url);
      },
    };
  } catch (error) {
    throw toOfflineStorageError(error, "cache_validation_failed");
  }
}

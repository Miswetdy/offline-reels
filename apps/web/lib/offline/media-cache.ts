import { OfflineStorageError, toOfflineStorageError } from "./errors";
import { getOfflineMediaPath, normalizeVideoId } from "./media-key";
import type { CachedVideoMetadata, CachedVideoValidation } from "./types";
import { isAllowedVideoContentType } from "./validation";

export const OFFLINE_MEDIA_CACHE_NAME = "offline-reels-media-v1";

function getCacheStorage(): CacheStorage {
  if (typeof caches === "undefined") {
    throw new OfflineStorageError("browser_storage_unavailable");
  }
  return caches;
}

async function openMediaCache(): Promise<Cache> {
  try {
    return await getCacheStorage().open(OFFLINE_MEDIA_CACHE_NAME);
  } catch (error) {
    throw toOfflineStorageError(error, "browser_storage_unavailable");
  }
}

function assertVideoResponse(response: Response): void {
  if (!isAllowedVideoContentType(response.headers.get("content-type") ?? "")) {
    throw new OfflineStorageError("unsupported_content_type");
  }
}

export function getMediaCacheKey(videoId: string): string {
  return getOfflineMediaPath(videoId);
}

export async function putCachedVideo(videoId: string, response: Response): Promise<void> {
  const cacheKey = getMediaCacheKey(videoId);
  assertVideoResponse(response);
  const cache = await openMediaCache();

  try {
    await cache.put(cacheKey, response.clone());
  } catch (error) {
    await cache.delete(cacheKey).catch(() => undefined);
    throw toOfflineStorageError(error, "cache_write_failed");
  }
}

/**
 * Transfers ownership of an unconsumed response body to Cache Storage.
 * The caller must not read or clone the response after this function is called.
 */
export async function putCachedVideoOwnedResponse(videoId: string, response: Response): Promise<void> {
  const cacheKey = getMediaCacheKey(videoId);
  assertVideoResponse(response);
  if (response.bodyUsed || response.body === null || [204, 205, 304].includes(response.status)) {
    throw new OfflineStorageError("cache_write_failed", new Error("The owned response body has already been consumed."));
  }
  const cache = await openMediaCache();

  try {
    await cache.put(cacheKey, response);
  } catch (error) {
    await cache.delete(cacheKey).catch(() => undefined);
    throw toOfflineStorageError(error, "cache_write_failed");
  }
}

export async function getCachedVideo(videoId: string): Promise<Response | undefined> {
  const cache = await openMediaCache();
  try {
    return (await cache.match(getMediaCacheKey(videoId))) ?? undefined;
  } catch (error) {
    throw toOfflineStorageError(error, "cache_write_failed");
  }
}

export async function hasCachedVideo(videoId: string): Promise<boolean> {
  return Boolean(await getCachedVideo(videoId));
}

export async function deleteCachedVideo(videoId: string): Promise<boolean> {
  const cache = await openMediaCache();
  try {
    return await cache.delete(getMediaCacheKey(videoId));
  } catch (error) {
    throw toOfflineStorageError(error, "cache_write_failed");
  }
}

export async function listCachedVideoIds(): Promise<string[]> {
  const cache = await openMediaCache();
  try {
    const keys = await cache.keys();
    const ids = keys.flatMap((request) => {
      const path = new URL(request.url).pathname;
      const prefix = "/offline-media/";
      if (!path.startsWith(prefix)) return [];

      try {
        const id = normalizeVideoId(decodeURIComponent(path.slice(prefix.length)));
        return getMediaCacheKey(id) === path ? [id] : [];
      } catch {
        return [];
      }
    });
    return ids.sort();
  } catch (error) {
    throw toOfflineStorageError(error, "cache_write_failed");
  }
}

export async function clearMediaCache(): Promise<boolean> {
  try {
    return await getCacheStorage().delete(OFFLINE_MEDIA_CACHE_NAME);
  } catch (error) {
    throw toOfflineStorageError(error, "browser_storage_unavailable");
  }
}

export async function validateCachedVideo(
  videoId: string,
  expected: CachedVideoMetadata,
): Promise<CachedVideoValidation> {
  const cacheKey = getMediaCacheKey(videoId);
  if (expected.cacheKey !== cacheKey) return { valid: false, reason: "cache_key_mismatch" };
  if (!isAllowedVideoContentType(expected.contentType)) {
    return { valid: false, reason: "invalid_content_type" };
  }

  const cached = await getCachedVideo(videoId);
  if (!cached) return { valid: false, reason: "missing" };
  if (!isAllowedVideoContentType(cached.headers.get("content-type") ?? "")) {
    return { valid: false, reason: "invalid_content_type" };
  }

  const byteSize = (await cached.blob()).size;
  if (byteSize !== expected.byteSize) return { valid: false, reason: "size_mismatch" };
  return { valid: true, byteSize };
}

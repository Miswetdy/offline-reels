import { assertVideoByteSize, validateVideoResponse } from './validation';

export const VIDEO_CACHE_NAME = 'offline-reels-spike-v1';

export function cacheKeyForVideo(id: string): string {
  return `/offline-reels-spike/videos/${encodeURIComponent(id)}`;
}

function getCacheStorage(): CacheStorage {
  if (!('caches' in window)) {
    throw new Error('Cache Storage is not available in this browser.');
  }

  return window.caches;
}

export async function saveVideoResponse(id: string, response: Response): Promise<{ cacheKey: string; byteSize: number }> {
  validateVideoResponse(response);

  const cacheKey = cacheKeyForVideo(id);
  const cache = await getCacheStorage().open(VIDEO_CACHE_NAME);
  try {
    await cache.put(cacheKey, response.clone());

    const cachedResponse = await cache.match(cacheKey);
    if (!cachedResponse) {
      throw new Error('The video was not found after caching.');
    }

    const byteSize = (await cachedResponse.blob()).size;
    assertVideoByteSize(byteSize);

    return { cacheKey, byteSize };
  } catch (error) {
    await cache.delete(cacheKey);
    throw error;
  }
}

export async function getCachedVideoBlob(cacheKey: string): Promise<Blob> {
  const cache = await getCacheStorage().open(VIDEO_CACHE_NAME);
  const response = await cache.match(cacheKey);
  if (!response) {
    throw new Error('The local video file is missing.');
  }

  return response.blob();
}

export async function hasCachedVideo(cacheKey: string): Promise<boolean> {
  const cache = await getCacheStorage().open(VIDEO_CACHE_NAME);
  return Boolean(await cache.match(cacheKey));
}

export async function deleteCachedVideo(cacheKey: string): Promise<void> {
  const cache = await getCacheStorage().open(VIDEO_CACHE_NAME);
  await cache.delete(cacheKey);
}

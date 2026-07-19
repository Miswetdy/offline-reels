import { describe, expect, it } from 'vitest';
import {
  cacheKeyForVideo,
  deleteCachedVideo,
  getCachedVideoBlob,
  hasCachedVideo,
  saveVideoResponse,
} from '../src/lib/cache-storage';

function mp4Response(body = 'test-video'): Response {
  return new Response(body, {
    status: 200,
    headers: {
      'content-type': 'video/mp4',
      'content-length': String(new TextEncoder().encode(body).byteLength),
    },
  });
}

describe('Cache Storage video persistence', () => {
  it('saves an MP4 response and reads it back by its stable cache key', async () => {
    const result = await saveVideoResponse('test-video-001', mp4Response());

    expect(result.cacheKey).toBe(cacheKeyForVideo('test-video-001'));
    expect(result.byteSize).toBe(10);
    expect(await hasCachedVideo(result.cacheKey)).toBe(true);
    const cachedBlob = await getCachedVideoBlob(result.cacheKey);
    expect(cachedBlob.size).toBe(10);
    expect(cachedBlob.type).toBe('video/mp4');
  });

  it('rejects a response that is not an MP4', async () => {
    await expect(
      saveVideoResponse(
        'test-video-001',
        new Response('not a video', { status: 200, headers: { 'content-type': 'text/plain' } }),
      ),
    ).rejects.toThrow('not an MP4');
  });

  it('removes an empty cached response when no content length is supplied', async () => {
    const cacheKey = cacheKeyForVideo('test-video-001');

    await expect(
      saveVideoResponse(
        'test-video-001',
        new Response('', { status: 200, headers: { 'content-type': 'video/mp4' } }),
      ),
    ).rejects.toThrow('video size is invalid');
    expect(await hasCachedVideo(cacheKey)).toBe(false);
  });

  it('deletes a saved video', async () => {
    const { cacheKey } = await saveVideoResponse('test-video-001', mp4Response());
    await deleteCachedVideo(cacheKey);

    expect(await hasCachedVideo(cacheKey)).toBe(false);
  });
});

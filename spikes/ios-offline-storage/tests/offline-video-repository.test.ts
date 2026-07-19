import { beforeEach, describe, expect, it, vi } from 'vitest';

const dependencies = vi.hoisted(() => ({
  cached: false,
  existing: undefined as unknown,
  saveMetadata: vi.fn(),
  deleteMetadata: vi.fn(),
  saveResponse: vi.fn(),
  deleteCached: vi.fn(),
}));

vi.mock('../src/lib/cache-storage', () => ({
  deleteCachedVideo: dependencies.deleteCached,
  getCachedVideoBlob: vi.fn(),
  hasCachedVideo: vi.fn(async () => dependencies.cached),
  saveVideoResponse: dependencies.saveResponse,
}));

vi.mock('../src/lib/indexed-db', () => ({
  deleteOfflineVideoMetadata: dependencies.deleteMetadata,
  getOfflineVideo: vi.fn(async () => dependencies.existing),
  listOfflineVideos: vi.fn(async () => []),
  saveOfflineVideo: dependencies.saveMetadata,
}));

import { downloadVideo } from '../src/lib/offline-video-repository';

const videoToDownload = {
  id: 'test-video-001',
  title: 'Test video',
  sourceUrl: '/media/sample.mp4',
};

describe('offline video repository', () => {
  beforeEach(() => {
    dependencies.cached = false;
    dependencies.existing = undefined;
    dependencies.saveMetadata.mockReset();
    dependencies.deleteMetadata.mockReset();
    dependencies.saveResponse.mockReset();
    dependencies.deleteCached.mockReset();
    dependencies.saveResponse.mockResolvedValue({
      cacheKey: '/offline-reels-spike/videos/test-video-001',
      byteSize: 12,
    });
  });

  it('does not download the same ready video twice', async () => {
    const existing = {
      id: 'test-video-001',
      cacheKey: '/offline-reels-spike/videos/test-video-001',
      title: 'Test video',
      mimeType: 'video/mp4' as const,
      byteSize: 12,
      downloadedAt: '2026-01-01T00:00:00.000Z',
    };
    dependencies.existing = existing;
    dependencies.cached = true;
    const fetchVideo = vi.fn();

    const result = await downloadVideo(videoToDownload, fetchVideo);

    expect(result).toEqual({ video: existing, alreadySaved: true });
    expect(fetchVideo).not.toHaveBeenCalled();
  });

  it('removes the cached file when saving metadata fails', async () => {
    dependencies.saveMetadata.mockRejectedValue(new Error('IndexedDB quota exceeded'));
    const fetchVideo = vi.fn(async () => new Response('video'));

    await expect(downloadVideo(videoToDownload, fetchVideo)).rejects.toThrow('IndexedDB quota exceeded');
    expect(dependencies.deleteCached).toHaveBeenCalledWith('/offline-reels-spike/videos/test-video-001');
  });

  it('persists a completed record without a temporary download status', async () => {
    const fetchVideo = vi.fn(async () => new Response('video'));

    await downloadVideo(videoToDownload, fetchVideo);

    expect(dependencies.saveMetadata).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'test-video-001', byteSize: 12 }),
    );
    expect(dependencies.saveMetadata.mock.calls[0]?.[0]).not.toHaveProperty('status');
  });
});

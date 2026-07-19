import { describe, expect, it } from 'vitest';
import {
  deleteOfflineVideoMetadata,
  getOfflineVideo,
  listOfflineVideos,
  saveOfflineVideo,
} from '../src/lib/indexed-db';
import type { OfflineVideo } from '../src/types/offline-video';

const savedVideo: OfflineVideo = {
  id: 'test-video-001',
  cacheKey: '/offline-reels-spike/videos/test-video-001',
  title: 'Test video',
  mimeType: 'video/mp4',
  byteSize: 128,
  downloadedAt: '2026-01-01T00:00:00.000Z',
};

describe('IndexedDB metadata persistence', () => {
  it('stores and restores only completed video metadata', async () => {
    await saveOfflineVideo(savedVideo);

    expect(await getOfflineVideo(savedVideo.id)).toEqual(savedVideo);
    expect(await listOfflineVideos()).toEqual([savedVideo]);
  });

  it('deletes a metadata record', async () => {
    await saveOfflineVideo(savedVideo);
    await deleteOfflineVideoMetadata(savedVideo.id);

    expect(await listOfflineVideos()).toEqual([]);
  });
});

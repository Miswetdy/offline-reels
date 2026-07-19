import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { OfflineVideo } from '../src/types/offline-video';

const dependencies = vi.hoisted(() => ({
  deleteVideo: vi.fn(),
  downloadVideo: vi.fn(),
  getStorageEstimate: vi.fn(),
  loadVideos: vi.fn(),
  readVideo: vi.fn(),
}));

vi.mock('../src/lib/offline-video-repository', () => ({
  deleteOfflineVideo: dependencies.deleteVideo,
  downloadVideo: dependencies.downloadVideo,
  loadOfflineVideos: dependencies.loadVideos,
  readOfflineVideo: dependencies.readVideo,
}));

vi.mock('../src/lib/storage-estimate', () => ({
  getStorageEstimate: dependencies.getStorageEstimate,
}));

import App from '../src/App';

const savedVideo: OfflineVideo = {
  id: 'test-video-001',
  cacheKey: '/offline-reels-spike/videos/test-video-001',
  title: 'Test video',
  mimeType: 'video/mp4',
  byteSize: 128,
  downloadedAt: '2026-01-01T00:00:00.000Z',
};

describe('App storage indicators', () => {
  beforeEach(() => {
    dependencies.deleteVideo.mockReset().mockResolvedValue(undefined);
    dependencies.downloadVideo.mockReset();
    dependencies.loadVideos.mockReset().mockResolvedValue([savedVideo]);
    dependencies.readVideo.mockReset();
    dependencies.getStorageEstimate
      .mockReset()
      .mockResolvedValueOnce({ usage: 1024 * 1024, quota: 1024 * 1024 })
      .mockResolvedValue({ usage: 0.3 * 1024 * 1024, quota: 1024 * 1024 });
  });

  it('sets the exact saved-video size to zero and refreshes the browser estimate after deletion', async () => {
    render(<App />);

    expect(await screen.findByText('128 B')).toBeTruthy();
    expect(screen.getByText(/Approximate browser storage used/).textContent).toContain('1.00 MB');

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(screen.getByText('0 B')).toBeTruthy());
    await waitFor(() => expect(dependencies.getStorageEstimate).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.getByText(/Approximate browser storage used/).textContent).toContain('0.30 MB'),
    );
    expect(screen.getByText('No videos are saved yet.')).toBeTruthy();
  });
});

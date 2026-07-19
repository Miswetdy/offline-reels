import type { OfflineVideo, VideoToDownload } from '../types/offline-video';
import {
  deleteCachedVideo,
  getCachedVideoBlob,
  hasCachedVideo,
  saveVideoResponse,
} from './cache-storage';
import {
  deleteOfflineVideoMetadata,
  getOfflineVideo,
  listOfflineVideos,
  saveOfflineVideo,
} from './indexed-db';
import { assertVideoDescriptor } from './validation';

export type DownloadResult = {
  video: OfflineVideo;
  alreadySaved: boolean;
};

export async function downloadVideo(
  videoToDownload: VideoToDownload,
  fetchVideo: typeof fetch = fetch,
): Promise<DownloadResult> {
  assertVideoDescriptor(videoToDownload.id, videoToDownload.title, videoToDownload.sourceUrl);

  const existing = await getOfflineVideo(videoToDownload.id);
  if (existing && (await hasCachedVideo(existing.cacheKey))) {
    return { video: existing, alreadySaved: true };
  }

  if (existing) {
    await deleteOfflineVideoMetadata(existing.id);
  }

  const response = await fetchVideo(videoToDownload.sourceUrl);
  const { cacheKey, byteSize } = await saveVideoResponse(videoToDownload.id, response);
  const offlineVideo: OfflineVideo = {
    id: videoToDownload.id,
    cacheKey,
    title: videoToDownload.title,
    mimeType: 'video/mp4',
    byteSize,
    downloadedAt: new Date().toISOString(),
  };

  try {
    await saveOfflineVideo(offlineVideo);
  } catch (error) {
    await deleteCachedVideo(cacheKey);
    throw error;
  }

  return { video: offlineVideo, alreadySaved: false };
}

export async function loadOfflineVideos(): Promise<OfflineVideo[]> {
  const metadata = await listOfflineVideos();
  const availableVideos: OfflineVideo[] = [];

  for (const video of metadata) {
    if (await hasCachedVideo(video.cacheKey)) {
      availableVideos.push(video);
    } else {
      await deleteOfflineVideoMetadata(video.id);
    }
  }

  return availableVideos;
}

export async function deleteOfflineVideo(video: OfflineVideo): Promise<void> {
  await deleteCachedVideo(video.cacheKey);
  await deleteOfflineVideoMetadata(video.id);
}

export async function readOfflineVideo(video: OfflineVideo): Promise<Blob> {
  return getCachedVideoBlob(video.cacheKey);
}

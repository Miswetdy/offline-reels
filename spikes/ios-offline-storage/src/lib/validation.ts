import type { OfflineVideo } from '../types/offline-video';

export const MAX_VIDEO_BYTES = 100 * 1024 * 1024;
const SAFE_VIDEO_ID = /^[a-z0-9][a-z0-9-]{0,63}$/;

export function assertVideoDescriptor(id: string, title: string, sourceUrl: string): void {
  if (!SAFE_VIDEO_ID.test(id)) {
    throw new Error('Video identifier is invalid.');
  }

  if (title.trim().length === 0 || title.length > 120) {
    throw new Error('Video title is invalid.');
  }

  let parsedUrl: URL;
  try {
    parsedUrl = new URL(sourceUrl, window.location.origin);
  } catch {
    throw new Error('Video URL is invalid.');
  }

  if (parsedUrl.origin !== window.location.origin) {
    throw new Error('Only same-origin test videos are allowed in this spike.');
  }
}

export function validateVideoResponse(response: Response): void {
  if (!response.ok) {
    throw new Error(`Video download failed with HTTP ${response.status}.`);
  }

  const contentType = response.headers.get('content-type')?.split(';', 1)[0].trim().toLowerCase();
  if (contentType !== 'video/mp4') {
    throw new Error('The downloaded file is not an MP4 video.');
  }

  const contentLength = response.headers.get('content-length');
  if (contentLength !== null) {
    assertVideoByteSize(Number(contentLength));
  }
}

export function assertVideoByteSize(byteSize: number): void {
  if (!Number.isSafeInteger(byteSize) || byteSize <= 0 || byteSize > MAX_VIDEO_BYTES) {
    throw new Error('The video size is invalid or exceeds the 100 MB spike limit.');
  }
}

export function assertOfflineVideo(video: OfflineVideo): void {
  if (
    !SAFE_VIDEO_ID.test(video.id) ||
    !video.cacheKey.startsWith('/offline-reels-spike/videos/') ||
    video.title.trim().length === 0 ||
    video.mimeType !== 'video/mp4' ||
    !Number.isSafeInteger(video.byteSize) ||
    video.byteSize <= 0
  ) {
    throw new Error('Offline video metadata is invalid.');
  }
}

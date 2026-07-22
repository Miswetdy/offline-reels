import { OfflineStorageError } from "./errors";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function normalizeVideoId(videoId: string): string {
  if (!UUID_PATTERN.test(videoId)) {
    throw new OfflineStorageError("invalid_video_id");
  }

  return videoId.toLowerCase();
}

export function getOfflineMediaPath(videoId: string): string {
  return `/offline-media/${normalizeVideoId(videoId)}`;
}

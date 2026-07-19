export type OfflineVideo = {
  id: string;
  cacheKey: string;
  title: string;
  mimeType: 'video/mp4';
  byteSize: number;
  downloadedAt: string;
  lastOpenedAt?: string;
};

export type VideoToDownload = {
  id: string;
  title: string;
  sourceUrl: string;
};

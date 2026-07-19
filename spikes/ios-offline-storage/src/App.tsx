import { useEffect, useMemo, useRef, useState } from 'react';
import { StorageSummary } from './components/storage-summary';
import { VideoCard } from './components/video-card';
import {
  deleteOfflineVideo,
  downloadVideo,
  loadOfflineVideos,
  readOfflineVideo,
} from './lib/offline-video-repository';
import { getStorageEstimate, type StorageEstimate } from './lib/storage-estimate';
import type { OfflineVideo, VideoToDownload } from './types/offline-video';

const testVideo: VideoToDownload = {
  id: 'test-video-001',
  title: 'Offline storage test video',
  sourceUrl: import.meta.env.VITE_SAMPLE_VIDEO_URL?.trim() || '/media/sample.mp4',
};

type OperationStatus =
  | { kind: 'idle'; message: string }
  | { kind: 'downloading'; message: string }
  | { kind: 'error'; message: string };

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'An unexpected error occurred.';
}

export default function App() {
  const [videos, setVideos] = useState<OfflineVideo[]>([]);
  const [status, setStatus] = useState<OperationStatus>({
    kind: 'idle',
    message: 'Ready to download a test MP4.',
  });
  const [estimate, setEstimate] = useState<StorageEstimate | null>(null);
  const [playingUrl, setPlayingUrl] = useState<string | null>(null);
  const [playingVideoId, setPlayingVideoId] = useState<string | null>(null);
  const currentObjectUrl = useRef<string | null>(null);
  const videoElement = useRef<HTMLVideoElement | null>(null);

  const savedBytes = useMemo(
    () => videos.reduce((total, video) => total + video.byteSize, 0),
    [videos],
  );
  const testVideoIsSaved = videos.some((video) => video.id === testVideo.id);
  const busy = status.kind === 'downloading';

  async function refreshStorageEstimate(): Promise<void> {
    setEstimate(await getStorageEstimate());
  }

  async function refresh(): Promise<void> {
    const [storedVideos, storageEstimate] = await Promise.all([loadOfflineVideos(), getStorageEstimate()]);
    setVideos(storedVideos);
    setEstimate(storageEstimate);
  }

  useEffect(() => {
    void refresh().catch((error: unknown) => {
      setStatus({ kind: 'error', message: errorMessage(error) });
    });
  }, []);

  useEffect(() => {
    if (!playingUrl || !videoElement.current) {
      return;
    }

    void videoElement.current.play().catch(() => {
      // iOS can require a second explicit user gesture; native controls stay available.
    });
  }, [playingUrl]);

  useEffect(() => {
    return () => {
      if (currentObjectUrl.current) {
        URL.revokeObjectURL(currentObjectUrl.current);
      }
    };
  }, []);

  async function handleDownload(): Promise<void> {
    setStatus({ kind: 'downloading', message: 'Downloading and saving the test video…' });
    try {
      const result = await downloadVideo(testVideo);
      await refresh();
      setStatus({
        kind: 'idle',
        message: result.alreadySaved ? 'The test video is already saved locally.' : 'Test video saved locally.',
      });
    } catch (error) {
      setStatus({ kind: 'error', message: errorMessage(error) });
    }
  }

  async function handlePlay(video: OfflineVideo): Promise<void> {
    try {
      const blob = await readOfflineVideo(video);
      if (currentObjectUrl.current) {
        URL.revokeObjectURL(currentObjectUrl.current);
      }

      const objectUrl = URL.createObjectURL(blob);
      currentObjectUrl.current = objectUrl;
      setPlayingVideoId(video.id);
      setPlayingUrl(objectUrl);
      setStatus({ kind: 'idle', message: 'Playing the video from local storage.' });
    } catch (error) {
      setStatus({ kind: 'error', message: errorMessage(error) });
    }
  }

  async function handleDelete(video: OfflineVideo): Promise<void> {
    try {
      await deleteOfflineVideo(video);
      setVideos((currentVideos) => currentVideos.filter((currentVideo) => currentVideo.id !== video.id));
      if (playingVideoId === video.id) {
        if (currentObjectUrl.current) {
          URL.revokeObjectURL(currentObjectUrl.current);
          currentObjectUrl.current = null;
        }
        setPlayingUrl(null);
        setPlayingVideoId(null);
      }
      await refreshStorageEstimate();
      setStatus({ kind: 'idle', message: 'Saved video deleted.' });
    } catch (error) {
      setStatus({ kind: 'error', message: errorMessage(error) });
    }
  }

  return (
    <main>
      <header>
        <p className="eyebrow">TASK-001</p>
        <h1>iOS offline video storage spike</h1>
        <p>
          This isolated PWA downloads one test MP4 into Cache Storage and keeps only successful metadata
          in IndexedDB.
        </p>
      </header>

      <StorageSummary savedBytes={savedBytes} estimate={estimate} />

      <section className="download-panel" aria-label="Download test video">
        <h2>Test video</h2>
        <p className="secondary">Source: {testVideo.sourceUrl}</p>
        <button type="button" onClick={() => void handleDownload()} disabled={busy || testVideoIsSaved}>
          {busy ? 'Downloading…' : testVideoIsSaved ? 'Saved locally' : 'Download test MP4'}
        </button>
        <p role="status" className={status.kind === 'error' ? 'status error' : 'status'}>
          {status.message}
        </p>
      </section>

      <section aria-label="Saved videos">
        <h2>Saved videos</h2>
        {videos.length === 0 ? (
          <p className="secondary">No videos are saved yet.</p>
        ) : (
          videos.map((video) => (
            <VideoCard
              key={video.id}
              video={video}
              onPlay={(selectedVideo) => void handlePlay(selectedVideo)}
              onDelete={(selectedVideo) => void handleDelete(selectedVideo)}
              disabled={busy}
            />
          ))
        )}
      </section>

      {playingUrl ? (
        <section className="player" aria-label="Offline video player">
          <h2>Local playback</h2>
          <video ref={videoElement} src={playingUrl} controls playsInline preload="metadata" />
        </section>
      ) : null}
    </main>
  );
}

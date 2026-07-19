import type { OfflineVideo } from '../types/offline-video';
import { formatBytes } from './storage-summary';

type VideoCardProps = {
  video: OfflineVideo;
  onPlay: (video: OfflineVideo) => void;
  onDelete: (video: OfflineVideo) => void;
  disabled: boolean;
};

export function VideoCard({ video, onPlay, onDelete, disabled }: VideoCardProps) {
  return (
    <article className="video-card">
      <div>
        <h2>{video.title}</h2>
        <p className="secondary">
          {formatBytes(video.byteSize)} · saved {new Date(video.downloadedAt).toLocaleString()}
        </p>
      </div>
      <div className="actions">
        <button type="button" onClick={() => onPlay(video)} disabled={disabled}>
          Play offline
        </button>
        <button type="button" className="danger" onClick={() => onDelete(video)} disabled={disabled}>
          Delete
        </button>
      </div>
    </article>
  );
}

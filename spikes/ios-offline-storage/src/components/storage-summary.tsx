import type { StorageEstimate } from '../lib/storage-estimate';

type StorageSummaryProps = {
  savedBytes: number;
  estimate: StorageEstimate | null;
};

export function formatBytes(byteSize: number): string {
  if (byteSize < 1024) {
    return `${byteSize} B`;
  }

  return `${(byteSize / 1024 / 1024).toFixed(2)} MB`;
}

export function StorageSummary({ savedBytes, estimate }: StorageSummaryProps) {
  return (
    <section className="storage-summary" aria-label="Storage summary">
      <p>
        Saved video files (exact): <strong>{formatBytes(savedBytes)}</strong>
      </p>
      {estimate?.usage !== undefined && estimate.quota !== undefined ? (
        <p className="secondary">
          Approximate browser storage used: {formatBytes(estimate.usage)} of {formatBytes(estimate.quota)}
          {' '}(includes the app shell, service worker, IndexedDB, and other origin data)
        </p>
      ) : (
        <p className="secondary">Approximate browser storage usage is unavailable.</p>
      )}
    </section>
  );
}

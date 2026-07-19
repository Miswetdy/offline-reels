import type { OfflineVideo } from '../types/offline-video';
import { assertOfflineVideo } from './validation';

const DATABASE_NAME = 'offline-reels-spike';
const DATABASE_VERSION = 1;
const VIDEO_STORE = 'videos';

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);

    request.onerror = () => reject(request.error ?? new Error('Unable to open IndexedDB.'));
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(VIDEO_STORE)) {
        request.result.createObjectStore(VIDEO_STORE, { keyPath: 'id' });
      }
    };
    request.onsuccess = () => resolve(request.result);
  });
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onerror = () => reject(request.error ?? new Error('IndexedDB request failed.'));
    request.onsuccess = () => resolve(request.result);
  });
}

async function runTransaction<T>(
  mode: IDBTransactionMode,
  action: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const database = await openDatabase();
  try {
    const transaction = database.transaction(VIDEO_STORE, mode);
    const result = await requestResult(action(transaction.objectStore(VIDEO_STORE)));
    await new Promise<void>((resolve, reject) => {
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error ?? new Error('IndexedDB transaction failed.'));
      transaction.onabort = () => reject(transaction.error ?? new Error('IndexedDB transaction was aborted.'));
    });
    return result;
  } finally {
    database.close();
  }
}

export async function saveOfflineVideo(video: OfflineVideo): Promise<void> {
  assertOfflineVideo(video);
  await runTransaction('readwrite', (store) => store.put(video));
}

export async function getOfflineVideo(id: string): Promise<OfflineVideo | undefined> {
  return runTransaction('readonly', (store) => store.get(id));
}

export async function listOfflineVideos(): Promise<OfflineVideo[]> {
  const videos = await runTransaction('readonly', (store) => store.getAll());
  return videos.sort((left, right) => right.downloadedAt.localeCompare(left.downloadedAt));
}

export async function deleteOfflineVideoMetadata(id: string): Promise<void> {
  await runTransaction('readwrite', (store) => store.delete(id));
}

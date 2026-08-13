import { openDB, type DBSchema, type IDBPDatabase } from "idb";

import { OfflineStorageError, toOfflineStorageError } from "./errors";
import type { LocalReserveRecord, OfflineVideoRecord, OfflineVideoStatus } from "./types";

export const OFFLINE_DATABASE_NAME = "offline-reels";
export const OFFLINE_DATABASE_VERSION = 2;
export const OFFLINE_VIDEO_STORE = "offlineVideos";
export const LOCAL_RESERVE_STORE = "localReserve";

export interface OfflineReelsDatabase extends DBSchema {
  offlineVideos: {
    key: string;
    value: OfflineVideoRecord;
    indexes: {
      statusUpdatedAt: [OfflineVideoStatus, string];
      completedDownloadedAt: [OfflineVideoStatus, string];
      lastWatchedAt: string;
    };
  };
  localReserve: {
    key: string;
    value: LocalReserveRecord;
  };
}

function assertIndexedDbAvailable(): void {
  if (typeof indexedDB === "undefined") {
    throw new OfflineStorageError("browser_storage_unavailable");
  }
}

export async function openOfflineDatabase(): Promise<IDBPDatabase<OfflineReelsDatabase>> {
  assertIndexedDbAvailable();

  try {
    return await openDB<OfflineReelsDatabase>(OFFLINE_DATABASE_NAME, OFFLINE_DATABASE_VERSION, {
      upgrade(database, oldVersion) {
        if (oldVersion < 1) {
          const store = database.createObjectStore(OFFLINE_VIDEO_STORE, { keyPath: "id" });
          store.createIndex("statusUpdatedAt", ["status", "updatedAt"]);
          store.createIndex("completedDownloadedAt", ["status", "downloadedAt"]);
          store.createIndex("lastWatchedAt", "lastWatchedAt");
        }
        if (oldVersion < 2) {
          database.createObjectStore(LOCAL_RESERVE_STORE, { keyPath: "id" });
        }
      },
    });
  } catch (error) {
    throw toOfflineStorageError(error, "browser_storage_unavailable");
  }
}

export async function withOfflineDatabase<T>(
  operation: (database: IDBPDatabase<OfflineReelsDatabase>) => Promise<T>,
): Promise<T> {
  const database = await openOfflineDatabase();
  try {
    return await operation(database);
  } catch (error) {
    throw toOfflineStorageError(error);
  } finally {
    database.close();
  }
}

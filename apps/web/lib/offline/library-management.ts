import { toOfflineStorageError } from "./errors";
import { clearMediaCache, deleteCachedVideo } from "./media-cache";
import { reconcileOfflineLibrary } from "./reconciliation";
import { clearOfflineVideos, deleteOfflineVideo } from "./repository";

async function recoverAfterMetadataFailure(error: unknown): Promise<never> {
  await reconcileOfflineLibrary().catch(() => undefined);
  throw toOfflineStorageError(error);
}

export async function deleteOfflineLibraryVideo(videoId: string): Promise<void> {
  await deleteCachedVideo(videoId);
  try {
    await deleteOfflineVideo(videoId);
  } catch (error) {
    await recoverAfterMetadataFailure(error);
  }
}

export async function clearOfflineLibrary(): Promise<void> {
  // Cache media is disposable; the metadata deletion uses its preserve flag so
  // a viewed ID and its durable sync outbox cannot be downloaded again.
  await clearMediaCache();
  try {
    await clearOfflineVideos(true);
  } catch (error) {
    await recoverAfterMetadataFailure(error);
  }
}

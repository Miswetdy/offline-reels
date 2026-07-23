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
  await clearMediaCache();
  try {
    await clearOfflineVideos();
  } catch (error) {
    await recoverAfterMetadataFailure(error);
  }
}

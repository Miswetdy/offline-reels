export type StorageEstimate = {
  usage?: number;
  quota?: number;
};

export async function getStorageEstimate(): Promise<StorageEstimate | null> {
  if (!navigator.storage?.estimate) {
    return null;
  }

  return navigator.storage.estimate();
}

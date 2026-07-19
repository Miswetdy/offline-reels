import 'fake-indexeddb/auto';
import { afterEach } from 'vitest';

class MemoryCache {
  private readonly entries = new Map<string, Response>();

  async match(request: RequestInfo | URL): Promise<Response | undefined> {
    const response = this.entries.get(this.key(request));
    return response?.clone();
  }

  async put(request: RequestInfo | URL, response: Response): Promise<void> {
    this.entries.set(this.key(request), response.clone());
  }

  async delete(request: RequestInfo | URL): Promise<boolean> {
    return this.entries.delete(this.key(request));
  }

  clear(): void {
    this.entries.clear();
  }

  private key(request: RequestInfo | URL): string {
    if (typeof request === 'string') {
      return new URL(request, window.location.origin).toString();
    }

    if (request instanceof URL) {
      return request.toString();
    }

    return request.url;
  }
}

const cachesByName = new Map<string, MemoryCache>();

Object.defineProperty(window, 'caches', {
  configurable: true,
  value: {
    open: async (name: string) => {
      let cache = cachesByName.get(name);
      if (!cache) {
        cache = new MemoryCache();
        cachesByName.set(name, cache);
      }
      return cache as unknown as Cache;
    },
  } as CacheStorage,
});

async function deleteSpikeDatabase(): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.deleteDatabase('offline-reels-spike');
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve();
    request.onblocked = () => resolve();
  });
}

afterEach(async () => {
  for (const cache of cachesByName.values()) {
    cache.clear();
  }
  await deleteSpikeDatabase();
});

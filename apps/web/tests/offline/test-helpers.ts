import { deleteDB } from "idb";

import { OFFLINE_DATABASE_NAME } from "../../lib/offline/db";

const TEST_ORIGIN = "https://offline-reels.test";

function toUrl(request: RequestInfo | URL): string {
  if (request instanceof Request) return request.url;
  return new URL(typeof request === "string" ? request : request.toString(), TEST_ORIGIN).toString();
}

class MemoryCache {
  private readonly entries = new Map<string, Response>();

  async match(request: RequestInfo | URL): Promise<Response | undefined> {
    return this.entries.get(toUrl(request))?.clone();
  }

  async put(request: RequestInfo | URL, response: Response): Promise<void> {
    this.entries.set(toUrl(request), response.clone());
  }

  async delete(request: RequestInfo | URL): Promise<boolean> {
    return this.entries.delete(toUrl(request));
  }

  async keys(): Promise<Request[]> {
    return [...this.entries.keys()].map((url) => new Request(url));
  }
}

export class MemoryCacheStorage {
  private readonly caches = new Map<string, MemoryCache>();

  async open(name: string): Promise<Cache> {
    let cache = this.caches.get(name);
    if (!cache) {
      cache = new MemoryCache();
      this.caches.set(name, cache);
    }
    return cache as unknown as Cache;
  }

  async delete(name: string): Promise<boolean> {
    return this.caches.delete(name);
  }

  async has(name: string): Promise<boolean> {
    return this.caches.has(name);
  }

  async keys(): Promise<string[]> {
    return [...this.caches.keys()];
  }
}

export function installFakeCacheStorage(): MemoryCacheStorage {
  const storage = new MemoryCacheStorage();
  Object.defineProperty(globalThis, "caches", { configurable: true, value: storage });
  return storage;
}

export async function resetOfflineDatabase(): Promise<void> {
  await deleteDB(OFFLINE_DATABASE_NAME);
}

export const VIDEO_ID_ONE = "11111111-1111-4111-8111-111111111111";
export const VIDEO_ID_TWO = "22222222-2222-4222-8222-222222222222";
export const VIDEO_ID_THREE = "33333333-3333-4333-8333-333333333333";

export function videoResponse(byteSize: number, contentType = "video/mp4"): Response {
  return new Response(new Uint8Array(byteSize).fill(7), { headers: { "content-type": contentType } });
}

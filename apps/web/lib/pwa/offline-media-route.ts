import { OFFLINE_MEDIA_CACHE_NAME } from "../offline/media-cache";
import { getOfflineMediaPath, normalizeVideoId } from "../offline/media-key";

export type OfflineMediaRouteRequest = {
  request: Request;
  url: URL;
  sameOrigin: boolean;
};

export type ByteRange = {
  start: number;
  end: number;
};

function createControlledResponse(status: number): Response {
  return new Response(null, {
    status,
    headers: { "cache-control": "no-store" },
  });
}

function isSafeDecimalInteger(value: string): boolean {
  if (!/^\d+$/.test(value)) return false;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed);
}

export function parseSingleByteRange(rangeHeader: string, totalSize: number): ByteRange | null {
  if (!Number.isSafeInteger(totalSize) || totalSize <= 0) return null;
  if (!rangeHeader.startsWith("bytes=")) return null;

  const rangeValue = rangeHeader.slice("bytes=".length);
  if (rangeValue === "" || rangeValue.includes(",")) return null;

  if (rangeValue.startsWith("-")) {
    const suffixValue = rangeValue.slice(1);
    if (!isSafeDecimalInteger(suffixValue)) return null;
    const suffixLength = Number(suffixValue);
    if (suffixLength <= 0) return null;
    return {
      start: Math.max(totalSize - suffixLength, 0),
      end: totalSize - 1,
    };
  }

  const match = /^(\d+)-(\d*)$/.exec(rangeValue);
  if (!match) return null;

  const [, startValue, endValue] = match;
  if (!isSafeDecimalInteger(startValue)) return null;
  const start = Number(startValue);
  if (start >= totalSize) return null;

  if (endValue === "") return { start, end: totalSize - 1 };
  if (!isSafeDecimalInteger(endValue)) return null;
  const requestedEnd = Number(endValue);
  if (requestedEnd < start) return null;
  return { start, end: Math.min(requestedEnd, totalSize - 1) };
}

function createMediaHeaders(response: Response, totalSize: number, range?: ByteRange): Headers {
  const headers = new Headers();
  for (const name of ["content-type", "cache-control", "etag", "last-modified"]) {
    const value = response.headers.get(name);
    if (value !== null) headers.set(name, value);
  }

  headers.set("accept-ranges", "bytes");
  if (range) {
    headers.set("content-length", String(range.end - range.start + 1));
    headers.set("content-range", `bytes ${range.start}-${range.end}/${totalSize}`);
  } else {
    headers.set("content-length", String(totalSize));
  }
  return headers;
}

function createRangeNotSatisfiableResponse(totalSize: number): Response {
  return new Response(null, {
    status: 416,
    headers: {
      "accept-ranges": "bytes",
      "content-range": `bytes */${totalSize}`,
      "cache-control": "no-store",
    },
  });
}

export function getOfflineMediaRouteVideoId(url: URL): string | null {
  if (url.search !== "") return null;

  const prefix = "/offline-media/";
  if (!url.pathname.startsWith(prefix)) return null;

  const encodedVideoId = url.pathname.slice(prefix.length);
  if (encodedVideoId === "" || encodedVideoId.includes("/")) return null;

  try {
    const videoId = normalizeVideoId(decodeURIComponent(encodedVideoId));
    return url.pathname === getOfflineMediaPath(videoId) ? videoId : null;
  } catch {
    return null;
  }
}

export function shouldHandleOfflineMediaRequest({ request, sameOrigin, url }: OfflineMediaRouteRequest): boolean {
  return (request.method === "GET" || request.method === "HEAD")
    && sameOrigin
    && getOfflineMediaRouteVideoId(url) !== null;
}

export async function handleOfflineMediaRequest(
  request: Request,
  cacheStorage: Pick<CacheStorage, "open"> | undefined = globalThis.caches,
): Promise<Response> {
  const videoId = getOfflineMediaRouteVideoId(new URL(request.url));
  if (videoId === null) return createControlledResponse(404);
  if (cacheStorage === undefined) return createControlledResponse(503);

  try {
    const mediaCache = await cacheStorage.open(OFFLINE_MEDIA_CACHE_NAME);
    const cached = await mediaCache.match(getOfflineMediaPath(videoId));
    if (!cached) return createControlledResponse(404);

    const bytes = new Uint8Array(await cached.arrayBuffer());
    const totalSize = bytes.byteLength;
    const rangeHeader = request.headers.get("range");
    const range = rangeHeader === null ? undefined : parseSingleByteRange(rangeHeader, totalSize);
    if (rangeHeader !== null && range === null) return createRangeNotSatisfiableResponse(totalSize);

    const parsedRange = range ?? undefined;
    const headers = createMediaHeaders(cached, totalSize, parsedRange);
    const isHead = request.method === "HEAD";
    if (!parsedRange) {
      return new Response(isHead ? null : bytes, { status: 200, headers });
    }

    const body = isHead ? null : bytes.slice(parsedRange.start, parsedRange.end + 1);
    return new Response(body, { status: 206, headers });
  } catch {
    return createControlledResponse(503);
  }
}

import { getApiUrl, isApiConfigurationError } from "./config";

export type Video = {
  id: string;
  title: string;
  content_type: string;
  byte_size: number;
  created_at: string;
};

export type VideoPage = {
  items: Video[];
  next_cursor: string | null;
};

export type GetVideosOptions = {
  limit?: number;
  cursor?: string | null;
  signal?: AbortSignal;
};

type FetchImplementation = typeof fetch;

export type VideoCatalogErrorKind = "network" | "http" | "response";

export class VideoCatalogError extends Error {
  constructor(readonly kind: VideoCatalogErrorKind) {
    super("Unable to load videos.");
    this.name = "VideoCatalogError";
  }
}

export function isVideoCatalogNetworkError(error: unknown): boolean {
  return error instanceof VideoCatalogError && error.kind === "network";
}

export async function getVideos(
  { limit = 5, cursor, signal }: GetVideosOptions = {},
  fetchImplementation: FetchImplementation = fetch,
): Promise<VideoPage> {
  const parameters = new URLSearchParams({ limit: String(limit) });
  if (cursor) {
    parameters.set("cursor", cursor);
  }
  let response: Response;
  try {
    response = await fetchImplementation(`${getApiUrl("/videos")}?${parameters.toString()}`, {
      cache: "no-store",
      signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new VideoCatalogError("network");
  }
  if (!response.ok) {
    throw new VideoCatalogError("http");
  }
  try {
    return (await response.json()) as VideoPage;
  } catch {
    throw new VideoCatalogError("response");
  }
}

export function getVideoStreamUrl(videoId: string): string {
  return `${getApiUrl("/videos")}/${encodeURIComponent(videoId)}/stream`;
}

export { isApiConfigurationError };

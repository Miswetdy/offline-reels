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

export const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function getVideos(
  { limit = 5, cursor, signal }: GetVideosOptions = {},
  fetchImplementation: FetchImplementation = fetch,
): Promise<VideoPage> {
  const parameters = new URLSearchParams({ limit: String(limit) });
  if (cursor) {
    parameters.set("cursor", cursor);
  }
  const response = await fetchImplementation(`${apiBaseUrl}/videos?${parameters.toString()}`, {
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    throw new Error("Unable to load videos.");
  }
  return (await response.json()) as VideoPage;
}

export function getVideoStreamUrl(videoId: string): string {
  return `${apiBaseUrl}/videos/${encodeURIComponent(videoId)}/stream`;
}

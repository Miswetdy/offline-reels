export type Video = {
  id: string;
  title: string;
  content_type: string;
  byte_size: number;
  created_at: string;
};

type FetchImplementation = typeof fetch;

export const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function getVideos(fetchImplementation: FetchImplementation = fetch): Promise<Video[]> {
  const response = await fetchImplementation(`${apiBaseUrl}/videos?limit=20`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Unable to load videos.");
  }
  return (await response.json()) as Video[];
}

export function getVideoStreamUrl(videoId: string): string {
  return `${apiBaseUrl}/videos/${encodeURIComponent(videoId)}/stream`;
}

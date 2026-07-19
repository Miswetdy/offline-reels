export type BackendAvailability = "checking" | "available" | "unavailable";

type FetchImplementation = typeof fetch;

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function checkBackendLive(fetchImplementation: FetchImplementation = fetch): Promise<BackendAvailability> {
  try {
    const response = await fetchImplementation(`${apiBaseUrl}/health/live`, {
      cache: "no-store",
    });

    return response.ok ? "available" : "unavailable";
  } catch {
    return "unavailable";
  }
}

import { getApiBaseUrl, isApiConfigurationError } from "./config";

export type BackendAvailability = "checking" | "available" | "unavailable" | "misconfigured";

type FetchImplementation = typeof fetch;

export async function checkBackendLive(fetchImplementation: FetchImplementation = fetch): Promise<BackendAvailability> {
  try {
    const apiBaseUrl = getApiBaseUrl();
    const response = await fetchImplementation(`${apiBaseUrl}/health/live`, {
      cache: "no-store",
    });

    return response.ok ? "available" : "unavailable";
  } catch (error) {
    if (isApiConfigurationError(error)) return "misconfigured";
    return "unavailable";
  }
}

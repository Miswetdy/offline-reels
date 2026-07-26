export class ApiConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiConfigurationError";
  }
}

/**
 * Returns the browser-facing Backend API base URL configured when the client
 * bundle is built. It can be either an origin or an origin with a path prefix
 * (for example, `https://host.ts.net/api`). The value is deliberately
 * required: a phone must not infer that its API is available on the phone's
 * own localhost.
 */
export function getApiBaseUrl(): string {
  const configuredValue = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (!configuredValue) {
    throw new ApiConfigurationError(
      "NEXT_PUBLIC_API_BASE_URL is not configured. Set the browser-facing Backend API URL before building the web app.",
    );
  }

  let url: URL;
  try {
    url = new URL(configuredValue);
  } catch {
    throw new ApiConfigurationError("NEXT_PUBLIC_API_BASE_URL must be an absolute HTTP(S) URL.");
  }

  if ((url.protocol !== "http:" && url.protocol !== "https:") || url.username || url.password || url.search || url.hash) {
    throw new ApiConfigurationError("NEXT_PUBLIC_API_BASE_URL must be an absolute HTTP(S) URL without credentials, query, or fragment.");
  }

  return url.href.replace(/\/$/, "");
}

/**
 * Builds an API endpoint URL without discarding an optional configured path
 * prefix. Endpoint paths are application-owned constants, never user input.
 */
export function getApiUrl(path: `/${string}`): string {
  return `${getApiBaseUrl()}/${path.replace(/^\/+/, "")}`;
}

export function isApiConfigurationError(error: unknown): error is ApiConfigurationError {
  return error instanceof ApiConfigurationError;
}

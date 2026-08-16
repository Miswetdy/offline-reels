/**
 * Browser-only client for the protected Stage 6 management control plane.
 *
 * Management calls intentionally use relative URLs: cookies are included only
 * for the current HTTPS origin and cannot follow a configured video API URL.
 * The CSRF capability stays in module memory and is cleared on an expired or
 * revoked session.  Never put it in storage, a URL, telemetry, or logs.
 */

export type ConnectionStatus = "disconnected" | "connecting" | "connected" | "reauth_required";
export type LoginStatus = "pending" | "active" | "completed" | "cancelled" | "expired" | "failed";
export type CollectionStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export type ManagementStatus = {
  connection_status: ConnectionStatus;
  reconnect_required: boolean;
  active_login: LoginSession | null;
  active_collection: CollectionRun | null;
  normalization: NormalizationStatus;
  ready_count: number;
  auto_collection: { enabled: boolean; target_reserve: number; scheduler_active: false };
};

export type LoginSession = { id: string; status: LoginStatus };
export type CollectionRun = {
  id: string;
  status: CollectionStatus;
  target: number;
  source_committed_count: number;
  already_available_count: number;
  failed_count: number;
  cancel_requested: boolean;
};

export type NormalizationStatus = {
  pending: number;
  running: number;
  completed: number;
  failed: number;
  cleanup_pending: number;
  ready_count: number;
};

export type ReserveSettings = {
  device_uuid: string;
  auto_refill_enabled: boolean;
  desired_count: number;
  low_watermark: number;
  quota_threshold: number;
};

export type ReserveReport = ReserveSettings & {
  local_completed_count: number;
  reported_at: string;
};

export type ReserveAggregateStatus = {
  reported_devices: number;
  local_completed_count: number;
  desired_count: number;
  collection_active: boolean;
};

export type ViewedReelSync = { device_uuid: string; events: Array<{ video_id: string }> };

export type ManagementErrorCode =
  | "unpaired"
  | "pairing_invalid"
  | "pairing_rate_limited"
  | "reauth_required"
  | "conflict"
  | "temporary"
  | "invalid_response";

export class ManagementApiError extends Error {
  constructor(readonly code: ManagementErrorCode) {
    super("Management request could not be completed.");
    this.name = "ManagementApiError";
  }
}

let csrfToken: string | null = null;
export const MANAGEMENT_REQUEST_TIMEOUT_MS = 15_000;

function managementUrl(path: string): string {
  if (typeof window === "undefined") throw new ManagementApiError("temporary");
  const url = new URL(path, window.location.origin);
  if (url.origin !== window.location.origin || !url.pathname.startsWith("/api/")) {
    throw new ManagementApiError("temporary");
  }
  return `${url.pathname}${url.search}`;
}

function isCsrf(value: unknown): value is string {
  return typeof value === "string" && value.length >= 16 && value.length <= 256;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function errorCode(status: number, payload: unknown, pairing = false): ManagementErrorCode {
  const code = isRecord(payload) && isRecord(payload.error) && typeof payload.error.code === "string"
    ? payload.error.code
    : "";
  if (status === 401) return pairing ? "pairing_invalid" : "unpaired";
  if (status === 429) return pairing ? "pairing_rate_limited" : "temporary";
  if (code === "reauth_required" || code === "account_not_connected") return "reauth_required";
  if (status === 409) return "conflict";
  return "temporary";
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  { pairing = false, mutation = false }: { pairing?: boolean; mutation?: boolean } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (mutation) {
    if (!csrfToken) throw new ManagementApiError("unpaired");
    headers.set("X-CSRF-Token", csrfToken);
    if (!headers.has("Idempotency-Key")) throw new ManagementApiError("temporary");
  }

  // iOS can keep a fetch alive across a PWA/service-worker update even after
  // the old proxy connection is gone. Bound every management request so a
  // visible dashboard never remains in its checking state indefinitely.
  const deadline = new AbortController();
  const abortFromCaller = () => deadline.abort();
  if (init.signal?.aborted) deadline.abort();
  else init.signal?.addEventListener("abort", abortFromCaller, { once: true });
  const timer = window.setTimeout(() => deadline.abort(), MANAGEMENT_REQUEST_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(managementUrl(path), {
      ...init,
      headers,
      cache: "no-store",
      credentials: "same-origin",
      signal: deadline.signal,
    });
  } catch {
    throw new ManagementApiError("temporary");
  } finally {
    window.clearTimeout(timer);
    init.signal?.removeEventListener("abort", abortFromCaller);
  }

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    if (!response.ok) throw new ManagementApiError(errorCode(response.status, null, pairing));
    throw new ManagementApiError("invalid_response");
  }
  if (!response.ok) {
    if (response.status === 401) clearManagementCredentials();
    throw new ManagementApiError(errorCode(response.status, payload, pairing));
  }
  return payload as T;
}

function mutationKey(): string {
  return crypto.randomUUID();
}

export function clearManagementCredentials(): void {
  csrfToken = null;
}

export function hasManagementCsrf(): boolean {
  return csrfToken !== null;
}

export async function exchangePairing(pairingSecret: string, signal?: AbortSignal): Promise<void> {
  const result = await request<{ csrf_token?: unknown }>("/api/management/pairing/exchange", {
    method: "POST",
    body: JSON.stringify({ pairing_secret: pairingSecret }),
    signal,
  }, { pairing: true });
  if (!isCsrf(result.csrf_token)) throw new ManagementApiError("invalid_response");
  csrfToken = result.csrf_token;
}

export async function refreshManagementSession(signal?: AbortSignal): Promise<boolean> {
  try {
    const result = await request<{ csrf_token?: unknown }>("/api/management/session", { signal });
    if (!isCsrf(result.csrf_token)) throw new ManagementApiError("invalid_response");
    csrfToken = result.csrf_token;
    return true;
  } catch (error) {
    if (error instanceof ManagementApiError && error.code === "unpaired") return false;
    throw error;
  }
}

export function getInstagramStatus(signal?: AbortSignal): Promise<ManagementStatus> {
  return request<ManagementStatus>("/api/instagram/status", { signal });
}

export function getLoginSession(loginId: string, signal?: AbortSignal): Promise<{ login_session: LoginSession }> {
  return request(`/api/instagram/login-sessions/${encodeURIComponent(loginId)}`, { signal });
}

export function createLoginSession(key = mutationKey()): Promise<{ login_session: LoginSession; launch_url?: string }> {
  return request("/api/instagram/login-sessions", {
    method: "POST",
    headers: { "Idempotency-Key": key },
  }, { mutation: true });
}

export function cancelLoginSession(loginId: string, key = mutationKey()): Promise<void> {
  return request(`/api/instagram/login-sessions/${encodeURIComponent(loginId)}/cancel`, {
    method: "POST",
    headers: { "Idempotency-Key": key },
  }, { mutation: true });
}

export function createCollectionRun(target: number, key = mutationKey()): Promise<{ collection_run: CollectionRun }> {
  return request("/api/instagram/collection-runs", {
    method: "POST",
    headers: { "Idempotency-Key": key },
    body: JSON.stringify({ target }),
  }, { mutation: true });
}

export function getCollectionRun(runId: string, signal?: AbortSignal): Promise<{ collection_run: CollectionRun }> {
  return request(`/api/instagram/collection-runs/${encodeURIComponent(runId)}`, { signal });
}

export function cancelCollectionRun(runId: string, key = mutationKey()): Promise<void> {
  return request(`/api/instagram/collection-runs/${encodeURIComponent(runId)}/cancel`, {
    method: "POST",
    headers: { "Idempotency-Key": key },
  }, { mutation: true });
}

export function getNormalizationStatus(signal?: AbortSignal): Promise<NormalizationStatus> {
  return request("/api/instagram/normalization-status", { signal });
}

export function getReserveSettings(deviceId: string, signal?: AbortSignal): Promise<{ reserve: Omit<ReserveReport, "device_uuid"> | null }> {
  return request(`/api/reserve/settings?device_uuid=${encodeURIComponent(deviceId)}`, { signal });
}

export function updateReserveSettings(settings: ReserveSettings, key = mutationKey()): Promise<{ reserve: Omit<ReserveReport, "device_uuid"> }> {
  return request("/api/reserve/settings", {
    method: "PUT",
    headers: { "Idempotency-Key": key },
    body: JSON.stringify(settings),
  }, { mutation: true });
}

export function reportReserve(report: ReserveReport, key = mutationKey()): Promise<{ reserve: Omit<ReserveReport, "device_uuid"> }> {
  return request("/api/reserve/reports", {
    method: "POST",
    headers: { "Idempotency-Key": key },
    body: JSON.stringify(report),
  }, { mutation: true });
}

export function getReserveStatus(signal?: AbortSignal): Promise<ReserveAggregateStatus> {
  return request("/api/reserve/status", { signal });
}

export function syncViewedReels(payload: ViewedReelSync, key = mutationKey()): Promise<{ confirmed_video_ids: string[] }> {
  return request("/api/instagram/views/sync", {
    method: "POST",
    headers: { "Idempotency-Key": key },
    body: JSON.stringify(payload),
  }, { mutation: true });
}

export function getConfirmedViewedReels(signal?: AbortSignal): Promise<{ confirmed_video_ids: string[] }> {
  return request("/api/instagram/views?limit=200", { signal });
}

export function getAccountCatalog(signal?: AbortSignal): Promise<{ items: Array<{ id: string; title: string; content_type: "video/mp4"; byte_size: number; created_at: string }> }> {
  return request("/api/instagram/catalog?limit=200", { signal });
}

export async function revokeManagementSession(key = mutationKey()): Promise<void> {
  await request("/api/management/session", {
    method: "DELETE",
    headers: { "Idempotency-Key": key },
  }, { mutation: true }).finally(clearManagementCredentials);
}

/** Only the Stage 4 gateway's exact local route may receive the one-time capability. */
export function getSafeLoginLaunchUrl(value: string): string {
  if (typeof window === "undefined") throw new ManagementApiError("invalid_response");
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new ManagementApiError("invalid_response");
  }
  if (
    url.protocol !== "https:"
    || url.origin !== window.location.origin
    || !/^\/connect\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(url.pathname)
    || !url.hash
    || url.search
  ) {
    throw new ManagementApiError("invalid_response");
  }
  return url.href;
}

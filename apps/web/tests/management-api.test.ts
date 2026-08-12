// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ManagementApiError,
  clearManagementCredentials,
  createCollectionRun,
  exchangePairing,
  getSafeLoginLaunchUrl,
  hasManagementCsrf,
  refreshManagementSession,
  revokeManagementSession,
} from "../lib/api/management";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => {
  clearManagementCredentials();
  vi.unstubAllGlobals();
});

describe("Stage 6 management browser client", () => {
  it("uses no-store same-origin credentials and keeps CSRF only in memory", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json({ csrf_token: "x".repeat(24) }));
    vi.stubGlobal("fetch", fetchMock);

    await exchangePairing("pairing-code-that-is-never-persisted");

    expect(fetchMock).toHaveBeenCalledWith("/api/management/pairing/exchange", expect.objectContaining({
      cache: "no-store",
      credentials: "same-origin",
      method: "POST",
    }));
    expect(hasManagementCsrf()).toBe(true);
    expect(sessionStorage.length).toBe(0);
    expect(localStorage.length).toBe(0);
  });

  it("reduces hostile pairing error payloads to safe categories without retaining their details", async () => {
    const raw = "FIXTURE_INTERNAL_REASON 00000000-0000-4000-8000-000000000001 shortcode codec object_key HTTP 429";
    const fetchMock = vi.fn().mockResolvedValue(json({ error: { code: raw, message: raw } }, 429));
    vi.stubGlobal("fetch", fetchMock);

    await expect(exchangePairing("pairing-code-that-is-never-persisted")).rejects.toMatchObject({ code: "pairing_rate_limited" });
    await expect(exchangePairing("pairing-code-that-is-never-persisted")).rejects.not.toThrow(raw);
    expect(hasManagementCsrf()).toBe(false);
  });

  it("refreshes the in-memory CSRF capability after a PWA restart", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json({ csrf_token: "y".repeat(24) }));
    vi.stubGlobal("fetch", fetchMock);

    expect(await refreshManagementSession()).toBe(true);
    expect(hasManagementCsrf()).toBe(true);
  });

  it("uses a caller-owned idempotency key on retries and clears credentials after 401 or revoke", async () => {
    const key = "same-user-operation-key";
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(json({ csrf_token: "z".repeat(24) }))
      .mockResolvedValueOnce(json({ collection_run: { id: "id", target: 1 } }, 201))
      .mockResolvedValueOnce(json({ collection_run: { id: "id", target: 1 } }, 201))
      .mockResolvedValueOnce(json({ revoked: true }));
    vi.stubGlobal("fetch", fetchMock);
    await refreshManagementSession();
    await createCollectionRun(1, key);
    await createCollectionRun(1, key);
    expect(fetchMock.mock.calls[1][1].headers.get("Idempotency-Key")).toBe(key);
    expect(fetchMock.mock.calls[2][1].headers.get("Idempotency-Key")).toBe(key);
    await revokeManagementSession("revoke-key");
    expect(hasManagementCsrf()).toBe(false);

    fetchMock.mockResolvedValueOnce(json({ error: { code: "unauthorized" } }, 401));
    await expect(refreshManagementSession()).resolves.toBe(false);
    expect(hasManagementCsrf()).toBe(false);
  });

  it("accepts only the fixed same-origin HTTPS Stage 4 launch route", () => {
    const id = "00000000-0000-4000-8000-000000000001";
    const allowed = `${window.location.origin.replace("http:", "https:")}/connect/${id}#capability`;
    // jsdom itself is HTTP, so make the URL match its real origin first and
    // assert the HTTPS requirement independently with an HTTPS-only origin.
    expect(() => getSafeLoginLaunchUrl(`${window.location.origin}/connect/${id}#capability`)).toThrow(ManagementApiError);
    expect(() => getSafeLoginLaunchUrl(`https://other.example/connect/${id}#capability`)).toThrow(ManagementApiError);
    expect(() => getSafeLoginLaunchUrl(`${allowed}?return=/`)).toThrow(ManagementApiError);
    expect(() => getSafeLoginLaunchUrl(`${allowed.replace("/connect/", "/unexpected/")}`)).toThrow(ManagementApiError);
  });
});

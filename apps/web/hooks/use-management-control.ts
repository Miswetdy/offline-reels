"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  ManagementApiError,
  cancelCollectionRun,
  cancelLoginSession,
  clearManagementCredentials,
  createCollectionRun,
  createLoginSession,
  exchangePairing,
  getInstagramStatus,
  getSafeLoginLaunchUrl,
  hasManagementCsrf,
  getNormalizationStatus,
  refreshManagementSession,
  revokeManagementSession,
  type ManagementStatus,
  type NormalizationStatus,
} from "../lib/api/management";
import { useNetworkStatus } from "./use-network-status";

export type ManagementUiState = "checking" | "unpaired" | "paired" | "temporary_error";

export type ManagementControl = {
  isOnline: boolean;
  state: ManagementUiState;
  busyElsewhere: boolean;
  status: ManagementStatus | null;
  error: ManagementApiError | null;
  pair: (code: string) => Promise<void>;
  disconnectDevice: () => Promise<void>;
  connectInstagram: () => Promise<void>;
  cancelInstagramLogin: () => Promise<void>;
  startCollection: (target: number, key: string) => Promise<{ id: string; target: number }>;
  cancelCollection: (runId: string, key: string) => Promise<void>;
  normalizationStatus: (signal?: AbortSignal) => Promise<NormalizationStatus>;
  refresh: () => Promise<ManagementStatus | null>;
};

const POLL_INTERVAL_MS = 3_000;

function asManagementError(error: unknown): ManagementApiError {
  return error instanceof ManagementApiError ? error : new ManagementApiError("temporary");
}

/**
 * Owns management-session refresh and bounded status polling.  It deliberately
 * does not persist credentials or run identifiers: a fresh page rebuilds its
 * safe state from the protected API.
 */
export function useManagementControl(): ManagementControl {
  const isOnline = useNetworkStatus();
  const [state, setState] = useState<ManagementUiState>("checking");
  const [status, setStatus] = useState<ManagementStatus | null>(null);
  const [error, setError] = useState<ManagementApiError | null>(null);
  const generationRef = useRef(0);
  const requestRef = useRef<AbortController | null>(null);
  const refreshingRef = useRef<Promise<ManagementStatus | null> | null>(null);
  const visibleRef = useRef(typeof document === "undefined" || document.visibilityState === "visible");
  const channelRef = useRef<BroadcastChannel | null>(null);
  const tabIdRef = useRef("");
  const remoteMutationRef = useRef(false);
  const [busyElsewhere, setBusyElsewhere] = useState(false);

  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    tabIdRef.current = crypto.randomUUID();
    const channel = new BroadcastChannel("offline-reels-management-ui-v1");
    channelRef.current = channel;
    channel.onmessage = (event: MessageEvent<unknown>) => {
      const message = event.data;
      if (typeof message !== "object" || message === null) return;
      const value = message as { source?: unknown; type?: unknown; active?: unknown };
      if (value.source === tabIdRef.current || value.type !== "mutation" || typeof value.active !== "boolean") return;
      remoteMutationRef.current = value.active;
      setBusyElsewhere(value.active);
    };
    return () => {
      channel.close();
      channelRef.current = null;
    };
  }, []);

  const runMutation = useCallback(async <T,>(operation: () => Promise<T>): Promise<T> => {
    if (remoteMutationRef.current) throw new ManagementApiError("conflict");
    channelRef.current?.postMessage({ type: "mutation", source: tabIdRef.current, active: true });
    try {
      return await operation();
    } finally {
      channelRef.current?.postMessage({ type: "mutation", source: tabIdRef.current, active: false });
    }
  }, []);

  const abortRequest = useCallback(() => {
    generationRef.current += 1;
    requestRef.current?.abort();
    requestRef.current = null;
  }, []);

  const refresh = useCallback(async (): Promise<ManagementStatus | null> => {
    if (!isOnline || !visibleRef.current) return null;
    if (refreshingRef.current) return refreshingRef.current;
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    const controller = new AbortController();
    requestRef.current?.abort();
    requestRef.current = controller;
    const work = (async () => {
      try {
        const paired = hasManagementCsrf() || await refreshManagementSession(controller.signal);
        if (!paired) {
          if (generation === generationRef.current && !controller.signal.aborted) {
            setState("unpaired");
            setStatus(null);
            setError(null);
          }
          return null;
        }
        const next = await getInstagramStatus(controller.signal);
        if (generation === generationRef.current && !controller.signal.aborted) {
          setState("paired");
          setStatus(next);
          setError(null);
        }
        return next;
      } catch (caught) {
        const nextError = asManagementError(caught);
        if (generation === generationRef.current && !controller.signal.aborted) {
          if (nextError.code === "unpaired") {
            setState("unpaired");
            setStatus(null);
          } else {
            setState("temporary_error");
          }
          setError(nextError);
        }
        return null;
      } finally {
        if (requestRef.current === controller) requestRef.current = null;
        refreshingRef.current = null;
      }
    })();
    refreshingRef.current = work;
    return work;
  }, [isOnline]);

  useEffect(() => {
    if (!isOnline) {
      abortRequest();
      return;
    }
    void refresh();
  }, [abortRequest, isOnline, refresh]);

  useEffect(() => {
    const onVisibility = () => {
      visibleRef.current = document.visibilityState === "visible";
      if (!visibleRef.current) abortRequest();
      else if (isOnline) void refresh();
    };
    const onPageHide = () => abortRequest();
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", onPageHide);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", onPageHide);
      abortRequest();
    };
  }, [abortRequest, isOnline, refresh]);

  useEffect(() => {
    if (!isOnline || state !== "paired") return;
    const timer = window.setInterval(() => {
      if (visibleRef.current) void refresh();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [isOnline, refresh, state]);

  const pair = useCallback(async (code: string) => {
    setError(null);
    try {
      await runMutation(() => exchangePairing(code));
      const next = await refresh();
      if (!next) throw new ManagementApiError("temporary");
    } catch (caught) {
      // Pairing errors are deliberately reduced to their safe client-side
      // category. Backend payloads, capability values, and HTTP details do
      // not enter React state or a user-facing message.
      const nextError = asManagementError(caught);
      setError(nextError);
      throw nextError;
    }
  }, [refresh, runMutation]);

  const disconnectDevice = useCallback(async () => {
    setError(null);
    await runMutation(() => revokeManagementSession());
    abortRequest();
    setStatus(null);
    // A concurrent status poll can have recorded a safe temporary failure
    // immediately before revoke completed. It must not survive as a pairing
    // error after the device has intentionally become unpaired.
    setError(null);
    setState("unpaired");
  }, [abortRequest, runMutation]);

  const connectInstagram = useCallback(async () => {
    setError(null);
    const result = await runMutation(() => createLoginSession());
    if (!result.launch_url) {
      await refresh();
      return;
    }
    // Validation happens before navigation.  The capability is never put in
    // React state, browser storage, a return URL, or an error message.
    window.location.assign(getSafeLoginLaunchUrl(result.launch_url));
  }, [refresh, runMutation]);

  const cancelInstagramLogin = useCallback(async () => {
    if (!status?.active_login) return;
    await runMutation(() => cancelLoginSession(status.active_login!.id));
    await refresh();
  }, [refresh, runMutation, status]);

  const startCollection = useCallback(async (target: number, key: string) => {
    const result = await runMutation(() => createCollectionRun(target, key));
    await refresh();
    return { id: result.collection_run.id, target: result.collection_run.target };
  }, [refresh, runMutation]);

  const cancelCollection = useCallback(async (runId: string, key: string) => {
    await runMutation(() => cancelCollectionRun(runId, key));
    await refresh();
  }, [refresh, runMutation]);

  return {
    isOnline,
    state,
    busyElsewhere,
    status,
    error,
    pair,
    disconnectDevice,
    connectInstagram,
    cancelInstagramLogin,
    startCollection,
    cancelCollection,
    normalizationStatus: getNormalizationStatus,
    refresh,
  };
}

export function clearManagementControlForTests(): void {
  clearManagementCredentials();
}

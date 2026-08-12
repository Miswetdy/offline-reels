"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { AppBottomNavigation } from "./app-bottom-navigation";
import { useManagementControl } from "../hooks/use-management-control";
import { useOfflineDownloads } from "../hooks/use-offline-downloads";
import { ManagementApiError, getCollectionRun } from "../lib/api/management";
import { getEntireVideoCatalog } from "../lib/api/videos";
import { getStorageEstimate, type LocalStorageEstimate } from "../lib/offline/storage";

export type StorageUsagePresentation = { label: string; percent: number | null };

const UNAVAILABLE_ESTIMATE: LocalStorageEstimate = { usage: null, quota: null, available: null, isAvailable: false };
// Production retains the Stage 7 bounded default. An explicitly built
// disposable staging image may lower it for a controlled live acceptance
// without changing the user-visible control plane or accepting a runtime URL
// parameter.
const configuredCollectionTarget = Number(process.env.NEXT_PUBLIC_STAGE7_COLLECTION_TARGET);
const COLLECTION_TARGET = Number.isInteger(configuredCollectionTarget)
  && configuredCollectionTarget >= 1
  && configuredCollectionTarget <= 10
  ? configuredCollectionTarget
  : 10;

type PipelineStage = "collecting" | "normalizing" | "downloading";
type Pipeline = { stage: PipelineStage; runId: string | null; target: number; percent: number | null; generation: number };

export function getStorageUsagePresentation(estimate: LocalStorageEstimate): StorageUsagePresentation {
  if (!estimate.isAvailable || estimate.usage === null || estimate.quota === null || estimate.quota <= 0) {
    return { label: "Не удалось определить заполненность хранилища", percent: null };
  }
  if (estimate.usage <= 0) return { label: "Хранилище не используется — 0%", percent: 0 };
  const percent = Math.min(100, Math.max(0, (estimate.usage / estimate.quota) * 100));
  return percent < 1
    ? { label: "Хранилище заполнено менее чем на 1%", percent }
    : { label: `Хранилище заполнено на ${Math.round(percent)}%`, percent };
}

function localProgressPercent(displayedBytes: number, totalBytes: number): number {
  if (totalBytes <= 0) return 0;
  return Math.min(100, Math.max(0, Math.round((displayedBytes / totalBytes) * 100)));
}

function collectionPercent(sourceCommitted: number, alreadyAvailable: number, target: number): number {
  if (target <= 0) return 0;
  return Math.min(100, Math.floor(((sourceCommitted + alreadyAvailable) / target) * 100));
}

function pairingErrorMessage(code: string | undefined): string | null {
  switch (code) {
    case "pairing_invalid": return "Код недействителен или срок его действия истёк.";
    case "pairing_rate_limited": return "Слишком много попыток. Попробуйте позже.";
    case "temporary": return "Не удалось подключить устройство. Попробуйте позже.";
    case "unpaired": return null;
    default: return null;
  }
}

function connectionPresentation(connection: string | undefined, reconnect: boolean): string {
  if (reconnect || connection === "reauth_required") return "Требуется переподключение Instagram";
  if (connection === "connected") return "Instagram подключён";
  if (connection === "connecting") return "Подключаем Instagram";
  return "Instagram не подключён";
}

function pipelineLabel(pipeline: Pipeline, localPercent: number | null): string {
  if (pipeline.stage === "collecting") return `Получаем Reels — ${pipeline.percent ?? 0}%`;
  if (pipeline.stage === "normalizing") return "Подготавливаем видео";
  return `Загружаем на устройство — ${localPercent ?? 0}%`;
}

export function LibraryDashboard() {
  const router = useRouter();
  const management = useManagementControl();
  const { snapshot, enqueueCatalogAndStart, cancelBatch, cancelAndClear } = useOfflineDownloads();
  const [estimate, setEstimate] = useState<LocalStorageEstimate>(UNAVAILABLE_ESTIMATE);
  const [pairingCode, setPairingCode] = useState("");
  const [pairingErrorCode, setPairingErrorCode] = useState<string | undefined>();
  const [pairingPending, setPairingPending] = useState(false);
  const [actionError, setActionError] = useState<"pipeline" | "clear" | "connection" | null>(null);
  const [pipeline, setPipeline] = useState<Pipeline | null>(null);
  const pipelineRef = useRef<Pipeline | null>(null);
  const pipelineAbortRef = useRef<AbortController | null>(null);
  const pipelineKeyRef = useRef<string | null>(null);
  const pipelineGenerationRef = useRef(0);

  const setCurrentPipeline = useCallback((next: Pipeline | null) => {
    pipelineRef.current = next;
    setPipeline(next);
  }, []);
  const refreshEstimate = useCallback(() => { void getStorageEstimate().then(setEstimate); }, []);

  useEffect(() => { refreshEstimate(); }, [refreshEstimate, snapshot?.completedCount, snapshot?.batchProgress?.state]);
  useEffect(() => {
    const abortPipelinePolling = () => pipelineAbortRef.current?.abort();
    window.addEventListener("pagehide", abortPipelinePolling);
    return () => {
      window.removeEventListener("pagehide", abortPipelinePolling);
      abortPipelinePolling();
    };
  }, []);
  useEffect(() => {
    if (!management.isOnline) pipelineAbortRef.current?.abort();
  }, [management.isOnline]);

  const currentPipeline = useCallback((generation: number) => {
    const current = pipelineRef.current;
    return current !== null
      && current.generation === generation
      && pipelineGenerationRef.current === generation
      && !pipelineAbortRef.current?.signal.aborted;
  }, []);

  const wait = useCallback((ms: number, signal: AbortSignal) => new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      window.clearTimeout(timer);
      reject(new DOMException("Cancelled", "AbortError"));
    }, { once: true });
  }), []);

  const startPipeline = useCallback(async () => {
    if (!management.isOnline || management.state !== "paired" || management.status?.connection_status !== "connected" || pipelineRef.current) return;
    setActionError(null);
    const controller = new AbortController();
    pipelineAbortRef.current?.abort();
    pipelineAbortRef.current = controller;
    const generation = pipelineGenerationRef.current + 1;
    pipelineGenerationRef.current = generation;
    // The key belongs to this user operation. A transient retry reuses it;
    // the ref is cleared after cancellation or terminal completion.
    pipelineKeyRef.current = crypto.randomUUID();
    setCurrentPipeline({ stage: "collecting", runId: null, target: COLLECTION_TARGET, percent: 0, generation });
    try {
      const created = await management.startCollection(COLLECTION_TARGET, pipelineKeyRef.current);
      if (!currentPipeline(generation)) return;
      setCurrentPipeline({ stage: "collecting", runId: created.id, target: created.target, percent: 0, generation });

      let delay = 800;
      while (currentPipeline(generation)) {
        const result = await getCollectionRun(created.id, controller.signal);
        if (!currentPipeline(generation)) return;
        const run = result.collection_run;
        setCurrentPipeline({
          stage: "collecting",
          runId: created.id,
          target: run.target,
          percent: collectionPercent(run.source_committed_count, run.already_available_count, run.target),
          generation,
        });
        if (run.status === "completed") break;
        if (run.status === "failed" || run.status === "cancelled") throw new Error("pipeline terminal");
        await wait(delay, controller.signal);
        delay = Math.min(8_000, delay * 2);
      }
      if (!currentPipeline(generation)) return;
      setCurrentPipeline({ stage: "normalizing", runId: created.id, target: created.target, percent: null, generation });

      delay = 1_000;
      while (currentPipeline(generation)) {
        const normalization = await management.normalizationStatus(controller.signal);
        if (!currentPipeline(generation)) return;
        // Stage 6 confirms active aggregate counters but does not expose a
        // per-run denominator. The UI therefore intentionally has no percent.
        if (normalization.pending === 0 && normalization.running === 0) break;
        await wait(delay, controller.signal);
        delay = Math.min(8_000, delay * 2);
      }
      if (!currentPipeline(generation)) return;
      const catalog = await getEntireVideoCatalog({ signal: controller.signal });
      if (!currentPipeline(generation)) return;
      const enqueued = await enqueueCatalogAndStart(catalog);
      if (!currentPipeline(generation)) return;
      if (enqueued === 0) {
        pipelineKeyRef.current = null;
        setCurrentPipeline(null);
        refreshEstimate();
        router.push("/offline");
        return;
      }
      setCurrentPipeline({ stage: "downloading", runId: null, target: created.target, percent: null, generation });
    } catch (error) {
      if (!currentPipeline(generation)) return;
      if (!(error instanceof DOMException && error.name === "AbortError")) setActionError("pipeline");
      pipelineKeyRef.current = null;
      setCurrentPipeline(null);
    }
  }, [currentPipeline, enqueueCatalogAndStart, management, refreshEstimate, router, setCurrentPipeline, wait]);

  const cancelPipeline = useCallback(() => {
    const current = pipelineRef.current;
    if (!current) {
      void cancelBatch();
      return;
    }
    pipelineGenerationRef.current += 1;
    pipelineAbortRef.current?.abort();
    setCurrentPipeline(null);
    const key = pipelineKeyRef.current ?? crypto.randomUUID();
    pipelineKeyRef.current = null;
    if (current.stage === "collecting" && current.runId) {
      void management.cancelCollection(current.runId, key).catch(() => undefined);
    } else if (current.stage === "downloading") {
      void cancelBatch();
    }
  }, [cancelBatch, management, setCurrentPipeline]);

  useEffect(() => {
    const batch = snapshot?.batchProgress;
    const current = pipelineRef.current;
    if (current?.stage !== "downloading" || !batch) return;
    const timer = window.setTimeout(() => {
      if (pipelineRef.current?.stage !== "downloading") return;
      if (batch.state === "completed") {
        pipelineKeyRef.current = null;
        setCurrentPipeline(null);
        refreshEstimate();
        router.push("/offline");
      } else if (batch.state === "failed") {
        pipelineKeyRef.current = null;
        setCurrentPipeline(null);
        setActionError("pipeline");
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refreshEstimate, router, setCurrentPipeline, snapshot?.batchProgress]);

  const pair = useCallback(() => {
    const code = pairingCode.trim();
    if (!code || pairingPending || !management.isOnline) return;
    setPairingErrorCode(undefined);
    setPairingPending(true);
    void management.pair(code).then(
      () => setPairingCode(""),
      (caught: unknown) => setPairingErrorCode(
        caught instanceof ManagementApiError ? caught.code : "temporary",
      ),
    ).finally(() => setPairingPending(false));
  }, [management, pairingCode, pairingPending]);

  const connect = useCallback(() => {
    setActionError(null);
    void management.connectInstagram().catch(() => setActionError("connection"));
  }, [management]);

  const clearLibrary = useCallback(() => {
    if (!window.confirm("Вы точно хотите удалить все скачанные Reels?")) return;
    if (pipelineRef.current?.stage === "downloading") cancelPipeline();
    setActionError(null);
    void cancelAndClear().then(refreshEstimate, () => setActionError("clear"));
  }, [cancelAndClear, cancelPipeline, refreshEstimate]);

  const storage = getStorageUsagePresentation(estimate);
  const storageWidth = storage.percent === null || storage.percent <= 0 ? 0 : Math.max(1, storage.percent);
  const batch = snapshot?.batchProgress ?? null;
  const localPercent = batch ? localProgressPercent(batch.displayedBytes, batch.totalBytes) : null;
  const active = pipeline ?? (batch?.state === "active" ? { stage: "downloading" as const, runId: null, target: 0, percent: null, generation: -1 } : null);
  const canStart = management.isOnline && management.state === "paired" && management.status?.connection_status === "connected" && !active && !management.busyElsewhere;
  // Only a pairing submission may render a pairing alert. Management polling,
  // reconnect, and a deliberate revoke must never leak an unrelated error into
  // the unpaired onboarding form.
  const pairingMessage = pairingErrorMessage(pairingErrorCode);
  const connection = connectionPresentation(management.status?.connection_status, management.status?.reconnect_required ?? false);

  return (
    <main className="mx-auto flex min-h-dvh max-w-lg flex-col px-5 pt-[calc(env(safe-area-inset-top)+2rem)] pb-[calc(var(--app-bottom-navigation-space)+1.5rem)]">
      <section className="space-y-7">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-950">Offline Reels</h1>
        <p className="text-sm font-medium text-slate-600" role="status" aria-live="polite">{management.isOnline ? "Онлайн" : "Нет подключения"}</p>

        {management.isOnline && management.state === "checking" ? <p role="status">Проверяем подключение устройства…</p> : null}
        {management.state === "unpaired" ? (
          <section className="space-y-3" aria-labelledby="pairing-heading">
            <h2 id="pairing-heading" className="text-xl font-semibold">Подключить это устройство</h2>
            <p className="text-sm text-slate-600">Введите одноразовый код, который подготовил оператор.</p>
            <label className="block text-sm font-medium" htmlFor="pairing-code">Одноразовый код</label>
            <input id="pairing-code" className="min-h-12 w-full rounded-xl border border-slate-300 px-3" value={pairingCode} onChange={(event) => setPairingCode(event.target.value)} autoComplete="off" disabled={!management.isOnline || pairingPending} />
            {pairingMessage ? <p role="alert" className="text-sm text-red-800">{pairingMessage}</p> : null}
            <button className="min-h-12 w-full rounded-xl bg-slate-950 px-5 py-3 font-semibold text-white disabled:opacity-50" type="button" disabled={!pairingCode.trim() || !management.isOnline || pairingPending || management.busyElsewhere} onClick={pair}>
              {pairingPending ? "Подключаем…" : "Подтвердить"}
            </button>
          </section>
        ) : null}

        {management.state === "paired" ? (
          <section className="space-y-3" aria-labelledby="instagram-heading">
            <h2 id="instagram-heading" className="text-xl font-semibold">Instagram</h2>
            <p role="status" aria-live="polite">{connection}</p>
            {management.status?.active_login ? <p role="status">Подготавливаем безопасный вход…</p> : null}
            {management.status?.connection_status === "connected" || management.status?.active_login ? null : (
              <button className="min-h-12 w-full rounded-xl border border-slate-300 px-5 py-3 font-semibold disabled:opacity-50" type="button" disabled={!management.isOnline || management.busyElsewhere} onClick={connect}>
                {management.status?.reconnect_required ? "Переподключить Instagram" : "Подключить Instagram"}
              </button>
            )}
            {management.status?.active_login ? <button className="min-h-11 rounded-xl border border-slate-300 px-4 py-2 font-medium" type="button" onClick={() => void management.cancelInstagramLogin()}>Отменить подключение</button> : null}
            {management.status?.auto_collection.scheduler_active === false ? <p className="text-sm text-slate-600">Автопополнение будет доступно позже</p> : null}
            <button className="min-h-11 rounded-xl border border-red-300 px-4 py-2 font-medium text-red-800" type="button" onClick={() => void management.disconnectDevice()}>Отключить это устройство</button>
          </section>
        ) : null}

        {active ? (
          <section className="space-y-3" aria-labelledby="pipeline-heading">
            <p id="pipeline-heading" className="font-medium" role="status" aria-live="polite">{pipelineLabel(active, localPercent)}</p>
            {active.stage !== "normalizing" ? <div className="h-2 overflow-hidden rounded-full bg-slate-200" role="progressbar" aria-label={pipelineLabel(active, localPercent).replace(/ — .*/, "")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={active.stage === "collecting" ? active.percent ?? 0 : localPercent ?? 0}><div className="h-full rounded-full bg-slate-900" style={{ width: `${active.stage === "collecting" ? active.percent ?? 0 : localPercent ?? 0}%` }} /></div> : null}
            <button className="min-h-11 rounded-xl border border-slate-300 px-4 py-2 font-medium" type="button" onClick={cancelPipeline}>Отменить загрузку</button>
          </section>
        ) : null}

        {actionError === "pipeline" ? <p role="alert" className="text-sm text-red-800">Не удалось завершить загрузку Reels. Попробуйте ещё раз.</p> : null}
        {management.isOnline && (actionError === "connection" || management.state === "temporary_error") ? <p role="alert" className="text-sm text-red-800">Временная безопасная ошибка. Попробуйте позже.</p> : null}
        {actionError === "clear" ? <p role="alert" className="text-sm text-red-800">Не удалось полностью очистить библиотеку. Попробуйте ещё раз.</p> : null}
        {management.busyElsewhere ? <p role="status" className="text-sm text-slate-600">Операция выполняется в другой вкладке.</p> : null}

        <section aria-labelledby="storage-heading" className="space-y-3">
          <h2 id="storage-heading" className="sr-only">Заполненность хранилища</h2>
          <p className="text-base font-medium text-slate-800">{storage.label}</p>
          <div className="h-2 overflow-hidden rounded-full bg-slate-200" role="progressbar" aria-label="Заполненность хранилища" aria-valuemin={0} aria-valuemax={100} aria-valuenow={storage.percent ?? undefined}><div className="h-full rounded-full bg-slate-900" style={{ width: `${storageWidth}%` }} /></div>
        </section>

        <button className="min-h-12 w-full rounded-xl bg-slate-950 px-5 py-3 font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-400" type="button" disabled={!canStart} onClick={() => void startPipeline()}>Загрузить Reels</button>
        <button className="min-h-11 w-full rounded-xl border border-red-300 px-5 py-3 font-medium text-red-800 disabled:opacity-50" type="button" disabled={snapshot?.clearing === true} onClick={clearLibrary}>Очистить библиотеку</button>
      </section>
      <AppBottomNavigation activeRoute="home" />
    </main>
  );
}

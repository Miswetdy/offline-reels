"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";

import { OfflineDownloadControls } from "./offline-download-controls";
import { AppBottomNavigation } from "./app-bottom-navigation";
import { NetworkStatusIndicator } from "./network-status-indicator";
import { VerticalVideoFeed, type VerticalVideoFeedItem } from "./vertical-video-feed";
import { useNetworkStatus } from "../hooks/use-network-status";
import {
  getVideoStreamUrl,
  getVideos,
  isApiConfigurationError,
  isVideoCatalogNetworkError,
  type Video,
} from "../lib/api/videos";

const PAGE_SIZE = 5;

type InitialState =
  | { status: "loading" }
  | { status: "error"; isNetworkFailure: boolean; isConfigurationError: boolean }
  | { status: "success" };

type NextPageState = "idle" | "loading" | "error";

function deduplicateVideos(existing: Video[], incoming: Video[]): Video[] {
  const seen = new Set(existing.map((video) => video.id));
  return [...existing, ...incoming.filter((video) => !seen.has(video.id))];
}

export function VideoList() {
  const isOnline = useNetworkStatus();
  const [initialState, setInitialState] = useState<InitialState>({ status: "loading" });
  const [videos, setVideos] = useState<Video[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [nextPageState, setNextPageState] = useState<NextPageState>("idle");
  const [activeVideoId, setActiveVideoId] = useState<string | null>(null);
  const [reloadAttempt, setReloadAttempt] = useState(0);

  const sentinelRef = useRef<HTMLDivElement>(null);
  const nextCursorRef = useRef<string | null>(null);
  const nextInFlightRef = useRef<string | null>(null);
  const nextAbortRef = useRef<AbortController | null>(null);

  const feedItems = useMemo<VerticalVideoFeedItem[]>(
    () => videos.map((video) => ({
      id: video.id,
      title: video.title,
      mediaUrl: getVideoStreamUrl(video.id),
      subtitle: `${video.byte_size.toLocaleString()} bytes`,
    })),
    [videos],
  );
  const effectiveActiveVideoId = activeVideoId ?? videos[0]?.id ?? null;

  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;
    nextCursorRef.current = null;

    getVideos({ limit: PAGE_SIZE, signal: controller.signal }).then(
      (page) => {
        if (disposed) return;
        setVideos(page.items);
        setNextCursor(page.next_cursor);
        nextCursorRef.current = page.next_cursor;
        setInitialState({ status: "success" });
      },
      (error: unknown) => {
        if (!disposed && !controller.signal.aborted) {
          setInitialState({
            status: "error",
            isNetworkFailure: isVideoCatalogNetworkError(error),
            isConfigurationError: isApiConfigurationError(error),
          });
        }
      },
    );
    return () => {
      disposed = true;
      controller.abort();
    };
  }, [reloadAttempt]);

  useEffect(() => {
    return () => nextAbortRef.current?.abort();
  }, []);

  const requestNextPage = useCallback(async () => {
    const cursor = nextCursorRef.current;
    if (cursor === null || nextInFlightRef.current !== null) return;

    const controller = new AbortController();
    nextInFlightRef.current = cursor;
    nextAbortRef.current = controller;
    setNextPageState("loading");
    try {
      const page = await getVideos({ limit: PAGE_SIZE, cursor, signal: controller.signal });
      if (controller.signal.aborted) return;
      setVideos((current) => deduplicateVideos(current, page.items));
      setNextCursor(page.next_cursor);
      nextCursorRef.current = page.next_cursor;
      setNextPageState("idle");
    } catch {
      if (!controller.signal.aborted) setNextPageState("error");
    } finally {
      if (nextInFlightRef.current === cursor) nextInFlightRef.current = null;
      if (nextAbortRef.current === controller) nextAbortRef.current = null;
    }
  }, []);

  const handleActiveItemChange = useCallback((item: VerticalVideoFeedItem | null) => {
    const itemId = item?.id ?? null;
    setActiveVideoId((current) => (current === itemId ? current : itemId));
  }, []);

  useEffect(() => {
    if (initialState.status !== "success" || nextCursor === null || nextPageState !== "idle") return;
    const sentinel = sentinelRef.current;
    const root = sentinel?.parentElement;
    if (root === null || sentinel === null) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) void requestNextPage();
      },
      { root, rootMargin: "0px 0px 100% 0px", threshold: 0 },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [initialState.status, nextCursor, nextPageState, requestNextPage]);

  if (initialState.status === "loading") {
    return <main className="grid h-dvh place-items-center" aria-live="polite">Loading videos…</main>;
  }
  if (initialState.status === "error") {
    if (initialState.isConfigurationError) {
      return (
        <main className="grid h-dvh place-items-center gap-4 p-6 text-center">
          <p role="alert">Backend API URL is not configured. Set NEXT_PUBLIC_API_BASE_URL and rebuild the web app.</p>
        </main>
      );
    }
    if (!isOnline || initialState.isNetworkFailure) {
      return (
        <main className="grid h-dvh place-items-center gap-4 p-6 text-center">
          <p role="alert">Нет подключения к сети. Онлайн-лента недоступна.</p>
          <Link className="rounded bg-slate-900 px-4 py-2 text-white" href="/offline">
            Открыть офлайн-библиотеку
          </Link>
          <button
            className="rounded border border-slate-900 px-4 py-2 disabled:opacity-50"
            type="button"
            disabled={!isOnline}
            onClick={() => {
              setInitialState({ status: "loading" });
              setVideos([]);
              setNextCursor(null);
              nextCursorRef.current = null;
              setReloadAttempt((value) => value + 1);
            }}
          >
            Повторить загрузку
          </button>
        </main>
      );
    }
    return (
      <main className="grid h-dvh place-items-center gap-4 p-6 text-center">
        <p role="alert">Unable to load videos.</p>
        <button
          className="rounded bg-slate-900 px-4 py-2 text-white"
          onClick={() => {
            setInitialState({ status: "loading" });
            setVideos([]);
            setNextCursor(null);
            nextCursorRef.current = null;
            setReloadAttempt((value) => value + 1);
          }}
        >
          Retry
        </button>
      </main>
    );
  }

  return (
    <>
      <aside className="fixed left-4 top-[calc(env(safe-area-inset-top)+1rem)] z-20 rounded bg-black/75 px-3 py-2 text-sm text-white">
        <NetworkStatusIndicator offlineMessage="Офлайн · онлайн-лента недоступна" />
      </aside>
      <VerticalVideoFeed
        items={feedItems}
        hasBottomNavigation
        emptyState={<main className="grid h-dvh place-items-center p-6">No videos are available yet.</main>}
        onActiveItemChange={handleActiveItemChange}
        footer={(
          <>
            {nextPageState === "loading" ? <p className="p-4 text-center" aria-live="polite">Loading more videos…</p> : null}
            {nextPageState === "error" ? (
              <div className="p-4 text-center" role="alert">
                <p>Unable to load more videos.</p>
                <button className="mt-2 rounded bg-white px-4 py-2 text-slate-950" type="button" onClick={() => void requestNextPage()}>
                  Retry loading more
                </button>
              </div>
            ) : null}
            {nextCursor === null ? <p className="p-4 text-center" aria-live="polite">You reached the end of the feed.</p> : null}
            <div ref={sentinelRef} data-testid="feed-sentinel" className="h-px shrink-0" aria-hidden="true" />
          </>
        )}
      />
      <OfflineDownloadControls videos={videos} activeVideoId={effectiveActiveVideoId} />
      <AppBottomNavigation activeRoute="videos" />
    </>
  );
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { OfflineDownloadControls } from "./offline-download-controls";
import { getVideoStreamUrl, getVideos, type Video } from "../lib/api/videos";

const PAGE_SIZE = 5;

type InitialState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "success" };

type NextPageState = "idle" | "loading" | "error";

function deduplicateVideos(existing: Video[], incoming: Video[]): Video[] {
  const seen = new Set(existing.map((video) => video.id));
  return [...existing, ...incoming.filter((video) => !seen.has(video.id))];
}

export function VideoList() {
  const [initialState, setInitialState] = useState<InitialState>({ status: "loading" });
  const [videos, setVideos] = useState<Video[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [nextPageState, setNextPageState] = useState<NextPageState>("idle");
  const [activeVideoId, setActiveVideoId] = useState<string | null>(null);
  const [muted, setMuted] = useState(true);
  const [playbackErrors, setPlaybackErrors] = useState<Record<string, boolean>>({});
  const [reloadAttempt, setReloadAttempt] = useState(0);

  const feedRef = useRef<HTMLElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef(new Map<string, HTMLElement>());
  const itemRefVersions = useRef(new Map<string, number>());
  const videoRefs = useRef(new Map<string, HTMLVideoElement>());
  const intersectionRatios = useRef(new Map<string, number>());
  const activeVideoIdRef = useRef<string | null>(null);
  const nextCursorRef = useRef<string | null>(null);
  const nextInFlightRef = useRef<string | null>(null);
  const nextAbortRef = useRef<AbortController | null>(null);
  const playbackGenerationRef = useRef(0);

  const effectiveActiveVideoId = activeVideoId ?? videos[0]?.id ?? null;
  const activeVideoIndex = videos.findIndex((video) => video.id === effectiveActiveVideoId);
  const nextVideoId = activeVideoIndex >= 0 ? videos[activeVideoIndex + 1]?.id ?? null : null;

  const mediaMode = useCallback(
    (videoId: string): "active" | "next" | "inactive" => {
      if (videoId === effectiveActiveVideoId) return "active";
      if (videoId === nextVideoId) return "next";
      return "inactive";
    },
    [effectiveActiveVideoId, nextVideoId],
  );

  const setCurrentActiveVideoId = useCallback((videoId: string) => {
    activeVideoIdRef.current = videoId;
    setActiveVideoId((current) => (current === videoId ? current : videoId));
  }, []);

  const closestVideoToFeedCenter = useCallback((): string | null => {
    const root = feedRef.current;
    if (root === null) return null;

    const rootRect = root.getBoundingClientRect();
    const rootCenter = rootRect.top + rootRect.height / 2;
    const currentActive = activeVideoIdRef.current;
    const candidates = videos
      .map((video, index) => {
        const item = itemRefs.current.get(video.id);
        if (item === undefined) return null;
        const rect = item.getBoundingClientRect();
        return { id: video.id, index, distance: Math.abs(rect.top + rect.height / 2 - rootCenter) };
      })
      .filter((candidate): candidate is { id: string; index: number; distance: number } => candidate !== null)
      .sort((first, second) => {
        if (first.distance !== second.distance) return first.distance - second.distance;
        if (first.id === currentActive) return -1;
        if (second.id === currentActive) return 1;
        return first.index - second.index;
      });

    return candidates[0]?.id ?? null;
  }, [videos]);

  const selectActiveVideoFromRatios = useCallback(() => {
    const candidates = videos
      .map((video, index) => ({
        id: video.id,
        index,
        ratio: intersectionRatios.current.get(video.id) ?? 0,
      }))
      .filter((candidate) => itemRefs.current.has(candidate.id));
    if (candidates.length === 0) return;

    const maximumRatio = Math.max(...candidates.map((candidate) => candidate.ratio));
    const highestRatioIds = new Set(
      candidates.filter((candidate) => candidate.ratio === maximumRatio).map((candidate) => candidate.id),
    );
    const centerCandidate = closestVideoToFeedCenter();
    if (centerCandidate !== null && highestRatioIds.has(centerCandidate)) {
      setCurrentActiveVideoId(centerCandidate);
      return;
    }

    const currentActive = activeVideoIdRef.current;
    if (currentActive !== null && highestRatioIds.has(currentActive)) {
      setCurrentActiveVideoId(currentActive);
      return;
    }
    setCurrentActiveVideoId(candidates.find((candidate) => candidate.ratio === maximumRatio)!.id);
  }, [closestVideoToFeedCenter, setCurrentActiveVideoId, videos]);

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
      () => {
        if (!disposed && !controller.signal.aborted) setInitialState({ status: "error" });
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

  useEffect(() => {
    if (initialState.status !== "success" || videos.length === 0) return;
    const root = feedRef.current;
    if (root === null) return;

    const videoIds = new Set(videos.map((video) => video.id));
    for (const videoId of intersectionRatios.current.keys()) {
      if (!videoIds.has(videoId)) {
        intersectionRatios.current.delete(videoId);
        itemRefs.current.delete(videoId);
        itemRefVersions.current.delete(videoId);
      }
    }
    for (const videoId of videoIds) {
      if (!intersectionRatios.current.has(videoId)) intersectionRatios.current.set(videoId, 0);
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const videoId = (entry.target as HTMLElement).dataset.videoId;
          if (videoId) intersectionRatios.current.set(videoId, entry.isIntersecting ? entry.intersectionRatio : 0);
        }
        selectActiveVideoFromRatios();
      },
      { root, threshold: [0, 0.25, 0.5, 0.75, 1] },
    );
    itemRefs.current.forEach((item) => observer.observe(item));
    if (activeVideoIdRef.current === null) setCurrentActiveVideoId(videos[0].id);
    return () => observer.disconnect();
  }, [initialState.status, selectActiveVideoFromRatios, setCurrentActiveVideoId, videos]);

  useEffect(() => {
    if (initialState.status !== "success" || videos.length === 0) return;
    const root = feedRef.current;
    if (root === null) return;

    let animationFrameId: number | null = null;
    const requestFrame = window.requestAnimationFrame ?? ((callback: FrameRequestCallback) => window.setTimeout(callback, 0));
    const cancelFrame = window.cancelAnimationFrame ?? window.clearTimeout;
    const handleScroll = () => {
      if (animationFrameId !== null) return;
      animationFrameId = requestFrame(() => {
        animationFrameId = null;
        const centerCandidate = closestVideoToFeedCenter();
        if (centerCandidate !== null && centerCandidate !== activeVideoIdRef.current) {
          setCurrentActiveVideoId(centerCandidate);
        }
      });
    };

    root.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      root.removeEventListener("scroll", handleScroll);
      if (animationFrameId !== null) cancelFrame(animationFrameId);
    };
  }, [closestVideoToFeedCenter, initialState.status, setCurrentActiveVideoId, videos.length]);

  useEffect(() => {
    videoRefs.current.forEach((video, videoId) => {
      const mode = mediaMode(videoId);
      const desiredSource = mode === "inactive" ? null : getVideoStreamUrl(videoId);
      video.muted = muted;
      video.preload = mode === "active" ? "auto" : mode === "next" ? "metadata" : "none";

      if (desiredSource === null) {
        if (video.hasAttribute("src")) {
          video.pause();
          video.removeAttribute("src");
          video.load();
        }
        return;
      }

      if (video.getAttribute("src") !== desiredSource) {
        video.src = desiredSource;
        video.load();
      }
    });
  }, [mediaMode, muted, videos]);

  useEffect(() => {
    const activeVideo = effectiveActiveVideoId
      ? videoRefs.current.get(effectiveActiveVideoId)
      : undefined;
    const generation = ++playbackGenerationRef.current;
    videoRefs.current.forEach((video, videoId) => {
      video.muted = muted;
      if (videoId !== effectiveActiveVideoId) video.pause();
    });
    if (!activeVideo || !effectiveActiveVideoId) return;

    const playActiveVideo = () => {
      if (generation !== playbackGenerationRef.current) return;
      void activeVideo.play().then(
        () => {
          if (generation !== playbackGenerationRef.current) activeVideo.pause();
        },
        () => {
          if (generation === playbackGenerationRef.current) {
            setPlaybackErrors((errors) => ({ ...errors, [effectiveActiveVideoId]: true }));
          }
        },
      );
    };

    let waitingForCanPlay = false;
    if (activeVideo.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
      playActiveVideo();
    } else {
      waitingForCanPlay = true;
      activeVideo.addEventListener("canplay", playActiveVideo, { once: true });
    }
    return () => {
      if (generation === playbackGenerationRef.current) playbackGenerationRef.current += 1;
      if (waitingForCanPlay) activeVideo.removeEventListener("canplay", playActiveVideo);
    };
  }, [effectiveActiveVideoId, muted, videos]);

  useEffect(() => {
    if (initialState.status !== "success" || nextCursor === null || nextPageState !== "idle") return;
    const root = feedRef.current;
    const sentinel = sentinelRef.current;
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

  const setItemRef = useCallback((videoId: string, element: HTMLElement | null) => {
    const version = (itemRefVersions.current.get(videoId) ?? 0) + 1;
    itemRefVersions.current.set(videoId, version);
    if (element) {
      itemRefs.current.set(videoId, element);
      if (!intersectionRatios.current.has(videoId)) intersectionRatios.current.set(videoId, 0);
      return;
    }
    queueMicrotask(() => {
      if (itemRefVersions.current.get(videoId) !== version) return;
      itemRefs.current.delete(videoId);
      intersectionRatios.current.delete(videoId);
      itemRefVersions.current.delete(videoId);
    });
  }, []);

  const setVideoRef = useCallback(
    (videoId: string) => (element: HTMLVideoElement | null) => {
      if (element) videoRefs.current.set(videoId, element);
      else {
        videoRefs.current.delete(videoId);
      }
    },
    [],
  );

  if (initialState.status === "loading") {
    return <main className="grid h-dvh place-items-center" aria-live="polite">Loading videos…</main>;
  }
  if (initialState.status === "error") {
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
  if (videos.length === 0) {
    return <main className="grid h-dvh place-items-center p-6">No videos are available yet.</main>;
  }

  return (
    <main ref={feedRef} className="relative h-dvh snap-y snap-mandatory overflow-y-auto bg-slate-950 text-white" aria-label="Video feed">
      <button
        className="fixed right-4 top-4 z-10 rounded-full bg-black/70 px-4 py-2 text-sm font-medium text-white focus:outline-2 focus:outline-offset-2 focus:outline-white"
        type="button"
        aria-label={muted ? "Turn sound on" : "Mute videos"}
        aria-pressed={!muted}
        onClick={() => setMuted((value) => !value)}
      >
        {muted ? "Unmute" : "Mute"}
      </button>
      <OfflineDownloadControls videos={videos} activeVideoId={effectiveActiveVideoId} />
      {videos.map((video) => (
        <section
          key={video.id}
          ref={(element) => setItemRef(video.id, element)}
          data-video-id={video.id}
          className="relative flex h-dvh snap-start snap-always items-center justify-center bg-black"
          aria-label={video.title}
        >
          <video
            ref={setVideoRef(video.id)}
            className="h-full w-full object-contain"
            controls
            muted={muted}
            playsInline
            preload={mediaMode(video.id) === "active" ? "auto" : mediaMode(video.id) === "next" ? "metadata" : "none"}
            onPlay={() => {
              setPlaybackErrors((errors) => ({ ...errors, [video.id]: false }));
              setCurrentActiveVideoId(video.id);
            }}
            onError={() => setPlaybackErrors((errors) => ({ ...errors, [video.id]: true }))}
          >
            Your browser does not support video playback.
          </video>
          <div className="pointer-events-none absolute bottom-8 left-4 right-4 rounded bg-black/60 p-3">
            <h2 className="font-semibold">{video.title}</h2>
            <p className="text-sm text-slate-200">{video.byte_size.toLocaleString()} bytes</p>
            {playbackErrors[video.id] ? (
              <p className="mt-1 text-sm text-amber-200" role="alert">This video could not be played.</p>
            ) : null}
          </div>
        </section>
      ))}
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
    </main>
  );
}

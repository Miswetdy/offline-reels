"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

export type VerticalVideoFeedItem = {
  id: string;
  title: string;
  mediaUrl: string;
  subtitle?: ReactNode;
};

type VerticalVideoFeedProps = {
  items: VerticalVideoFeedItem[];
  emptyState?: ReactNode;
  footer?: ReactNode;
  renderActions?: (item: VerticalVideoFeedItem) => ReactNode;
  onActiveItemChange?: (item: VerticalVideoFeedItem | null) => void;
};

type MediaMode = "previous" | "active" | "next" | "inactive";
type PlaybackErrorKind = "media" | "autoplay";

export function VerticalVideoFeed({
  items,
  emptyState,
  footer,
  renderActions,
  onActiveItemChange,
}: VerticalVideoFeedProps) {
  const [activeItemId, setActiveItemId] = useState<string | null>(null);
  const [lastActiveIndex, setLastActiveIndex] = useState(0);
  const [muted, setMuted] = useState(true);
  const [playbackErrors, setPlaybackErrors] = useState<Record<string, PlaybackErrorKind>>({});

  const feedRef = useRef<HTMLElement>(null);
  const itemRefs = useRef(new Map<string, HTMLElement>());
  const itemRefVersions = useRef(new Map<string, number>());
  const videoRefs = useRef(new Map<string, HTMLVideoElement>());
  const intersectionRatios = useRef(new Map<string, number>());
  const activeItemIdRef = useRef<string | null>(null);
  const lastPlaybackActiveItemIdRef = useRef<string | null>(null);
  const playbackGenerationRef = useRef(0);

  const activeItemStillExists = activeItemId !== null && items.some((item) => item.id === activeItemId);
  const fallbackActiveItemId = items[Math.min(lastActiveIndex, items.length - 1)]?.id ?? null;
  const effectiveActiveItemId = activeItemStillExists ? activeItemId : fallbackActiveItemId;
  const activeItemIndex = items.findIndex((item) => item.id === effectiveActiveItemId);
  const previousItemId = activeItemIndex > 0 ? items[activeItemIndex - 1]?.id ?? null : null;
  const nextItemId = activeItemIndex >= 0 ? items[activeItemIndex + 1]?.id ?? null : null;

  const mediaMode = useCallback(
    (itemId: string): MediaMode => {
      if (itemId === effectiveActiveItemId) return "active";
      if (itemId === previousItemId) return "previous";
      if (itemId === nextItemId) return "next";
      return "inactive";
    },
    [effectiveActiveItemId, nextItemId, previousItemId],
  );

  const sourceMode = useCallback(
    (itemId: string): MediaMode => playbackErrors[itemId] === "media" ? "inactive" : mediaMode(itemId),
    [mediaMode, playbackErrors],
  );

  const setCurrentActiveItemId = useCallback((itemId: string | null) => {
    activeItemIdRef.current = itemId;
    setActiveItemId((current) => (current === itemId ? current : itemId));
    const itemIndex = itemId === null ? -1 : items.findIndex((item) => item.id === itemId);
    if (itemIndex >= 0) setLastActiveIndex(itemIndex);
  }, [items]);

  useEffect(() => {
    activeItemIdRef.current = effectiveActiveItemId;
  }, [effectiveActiveItemId]);

  const closestItemToFeedCenter = useCallback((): string | null => {
    const root = feedRef.current;
    if (root === null) return null;

    const rootRect = root.getBoundingClientRect();
    const rootCenter = rootRect.top + rootRect.height / 2;
    const currentActive = activeItemIdRef.current;
    const candidates = items
      .map((item, index) => {
        const element = itemRefs.current.get(item.id);
        if (element === undefined) return null;
        const rect = element.getBoundingClientRect();
        return { id: item.id, index, distance: Math.abs(rect.top + rect.height / 2 - rootCenter) };
      })
      .filter((candidate): candidate is { id: string; index: number; distance: number } => candidate !== null)
      .sort((first, second) => {
        if (first.distance !== second.distance) return first.distance - second.distance;
        if (first.id === currentActive) return -1;
        if (second.id === currentActive) return 1;
        return first.index - second.index;
      });

    return candidates[0]?.id ?? null;
  }, [items]);

  const selectActiveItemFromRatios = useCallback(() => {
    const candidates = items
      .map((item, index) => ({
        id: item.id,
        index,
        ratio: intersectionRatios.current.get(item.id) ?? 0,
      }))
      .filter((candidate) => itemRefs.current.has(candidate.id));
    if (candidates.length === 0) return;

    const maximumRatio = Math.max(...candidates.map((candidate) => candidate.ratio));
    const highestRatioIds = new Set(
      candidates.filter((candidate) => candidate.ratio === maximumRatio).map((candidate) => candidate.id),
    );
    const centerCandidate = closestItemToFeedCenter();
    if (centerCandidate !== null && highestRatioIds.has(centerCandidate)) {
      setCurrentActiveItemId(centerCandidate);
      return;
    }

    const currentActive = activeItemIdRef.current;
    if (currentActive !== null && highestRatioIds.has(currentActive)) {
      setCurrentActiveItemId(currentActive);
      return;
    }
    setCurrentActiveItemId(candidates.find((candidate) => candidate.ratio === maximumRatio)!.id);
  }, [closestItemToFeedCenter, items, setCurrentActiveItemId]);

  useEffect(() => {
    const activeItem = items.find((item) => item.id === effectiveActiveItemId) ?? null;
    onActiveItemChange?.(activeItem);
  }, [effectiveActiveItemId, items, onActiveItemChange]);

  useEffect(() => {
    if (items.length === 0) return;
    const root = feedRef.current;
    if (root === null) return;

    const itemIds = new Set(items.map((item) => item.id));
    for (const itemId of intersectionRatios.current.keys()) {
      if (!itemIds.has(itemId)) {
        intersectionRatios.current.delete(itemId);
        itemRefs.current.delete(itemId);
        itemRefVersions.current.delete(itemId);
      }
    }
    for (const itemId of itemIds) {
      if (!intersectionRatios.current.has(itemId)) intersectionRatios.current.set(itemId, 0);
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const itemId = (entry.target as HTMLElement).dataset.videoId;
          if (itemId) intersectionRatios.current.set(itemId, entry.isIntersecting ? entry.intersectionRatio : 0);
        }
        selectActiveItemFromRatios();
      },
      { root, threshold: [0, 0.25, 0.5, 0.75, 1] },
    );
    itemRefs.current.forEach((item) => observer.observe(item));
    if (activeItemIdRef.current === null) setCurrentActiveItemId(items[0].id);
    return () => observer.disconnect();
  }, [items, selectActiveItemFromRatios, setCurrentActiveItemId]);

  useEffect(() => {
    if (items.length === 0) return;
    const root = feedRef.current;
    if (root === null) return;

    let animationFrameId: number | null = null;
    const requestFrame = window.requestAnimationFrame ?? ((callback: FrameRequestCallback) => window.setTimeout(callback, 0));
    const cancelFrame = window.cancelAnimationFrame ?? window.clearTimeout;
    const handleScroll = () => {
      if (animationFrameId !== null) return;
      animationFrameId = requestFrame(() => {
        animationFrameId = null;
        const centerCandidate = closestItemToFeedCenter();
        if (centerCandidate !== null && centerCandidate !== activeItemIdRef.current) {
          setCurrentActiveItemId(centerCandidate);
        }
      });
    };

    root.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      root.removeEventListener("scroll", handleScroll);
      if (animationFrameId !== null) cancelFrame(animationFrameId);
    };
  }, [closestItemToFeedCenter, items.length, setCurrentActiveItemId]);

  const clearVideoSource = useCallback((video: HTMLVideoElement) => {
    if (video.hasAttribute("src")) {
      video.pause();
      video.removeAttribute("src");
      video.load();
    }
  }, []);

  const markMediaFailed = useCallback((itemId: string, video: HTMLVideoElement) => {
    playbackGenerationRef.current += 1;
    clearVideoSource(video);
    setPlaybackErrors((errors) => errors[itemId] === "media" ? errors : { ...errors, [itemId]: "media" });
  }, [clearVideoSource]);

  const pauseAllVideos = useCallback(() => {
    playbackGenerationRef.current += 1;
    videoRefs.current.forEach((video) => video.pause());
  }, []);

  useEffect(() => {
    const pauseForBackground = () => pauseAllVideos();
    const handleVisibilityChange = () => {
      if (document.visibilityState === "hidden") pauseForBackground();
    };
    // A restored page keeps its catalog and position. It deliberately does not
    // call play(): browsers may reject background/resume autoplay.
    const handlePageShow = () => pauseForBackground();

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("pagehide", pauseForBackground);
    window.addEventListener("pageshow", handlePageShow);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("pagehide", pauseForBackground);
      window.removeEventListener("pageshow", handlePageShow);
    };
  }, [pauseAllVideos]);

  useEffect(() => () => {
    pauseAllVideos();
    videoRefs.current.forEach(clearVideoSource);
  }, [clearVideoSource, pauseAllVideos]);

  useEffect(() => {
    const desiredItems = items.filter((item) => sourceMode(item.id) !== "inactive");

    videoRefs.current.forEach((video, itemId) => {
      const item = items.find((candidate) => candidate.id === itemId);
      if (!item) return;
      const mode = sourceMode(itemId);
      video.muted = muted;
      video.preload = mode === "active" ? "auto" : mode === "inactive" ? "none" : "metadata";
      if (mode === "inactive") clearVideoSource(video);
    });

    desiredItems.forEach((item) => {
      const video = videoRefs.current.get(item.id);
      if (video && video.getAttribute("src") !== item.mediaUrl) {
        video.src = item.mediaUrl;
        video.load();
      }
    });
  }, [clearVideoSource, items, muted, sourceMode]);

  useEffect(() => {
    const activeVideo = effectiveActiveItemId ? videoRefs.current.get(effectiveActiveItemId) : undefined;
    const generation = ++playbackGenerationRef.current;
    const isNewActiveItem = lastPlaybackActiveItemIdRef.current !== effectiveActiveItemId;
    lastPlaybackActiveItemIdRef.current = effectiveActiveItemId;
    videoRefs.current.forEach((video, itemId) => {
      video.muted = muted;
      if (itemId !== effectiveActiveItemId) video.pause();
    });
    if (!activeVideo || !effectiveActiveItemId) return;

    let resetBeforePlay = isNewActiveItem;
    const playActiveVideo = () => {
      if (generation !== playbackGenerationRef.current) return;
      if (resetBeforePlay) {
        activeVideo.currentTime = 0;
        resetBeforePlay = false;
      }
      void activeVideo.play().then(
        () => {
          if (generation !== playbackGenerationRef.current) activeVideo.pause();
        },
        () => {
          if (generation === playbackGenerationRef.current) {
            setPlaybackErrors((errors) => ({ ...errors, [effectiveActiveItemId]: "autoplay" }));
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
  }, [effectiveActiveItemId, items, muted]);

  const setItemRef = useCallback((itemId: string, element: HTMLElement | null) => {
    const version = (itemRefVersions.current.get(itemId) ?? 0) + 1;
    itemRefVersions.current.set(itemId, version);
    if (element) {
      itemRefs.current.set(itemId, element);
      if (!intersectionRatios.current.has(itemId)) intersectionRatios.current.set(itemId, 0);
      return;
    }
    queueMicrotask(() => {
      if (itemRefVersions.current.get(itemId) !== version) return;
      itemRefs.current.delete(itemId);
      intersectionRatios.current.delete(itemId);
      itemRefVersions.current.delete(itemId);
    });
  }, []);

  const setVideoRef = useCallback(
    (itemId: string) => (element: HTMLVideoElement | null) => {
      if (element) videoRefs.current.set(itemId, element);
      else videoRefs.current.delete(itemId);
    },
    [],
  );

  if (items.length === 0) {
    return <>{emptyState ?? <main className="grid h-dvh place-items-center p-6">No videos are available yet.</main>}</>;
  }

  return (
    <main ref={feedRef} className="relative h-dvh snap-y snap-mandatory overflow-y-auto bg-slate-950 text-white" aria-label="Video feed">
      <button
        className="fixed right-4 top-[calc(env(safe-area-inset-top)+1rem)] z-10 rounded-full bg-black/70 px-4 py-2 text-sm font-medium text-white focus:outline-2 focus:outline-offset-2 focus:outline-white"
        type="button"
        aria-label={muted ? "Turn sound on" : "Mute videos"}
        aria-pressed={!muted}
        onClick={() => setMuted((value) => !value)}
      >
        {muted ? "Unmute" : "Mute"}
      </button>
      {items.map((item) => (
        <section
          key={item.id}
          ref={(element) => setItemRef(item.id, element)}
          data-video-id={item.id}
          className="relative flex h-dvh snap-start snap-always items-center justify-center bg-black"
          aria-label={item.title}
        >
          <video
            ref={setVideoRef(item.id)}
            className="h-full w-full object-contain"
            controls
            muted={muted}
            playsInline
            preload={sourceMode(item.id) === "active" ? "auto" : sourceMode(item.id) === "inactive" ? "none" : "metadata"}
            aria-busy={sourceMode(item.id) !== "inactive" && playbackErrors[item.id] !== "media"}
            onPlay={() => {
              setPlaybackErrors((errors) => {
                if (errors[item.id] === undefined) return errors;
                const nextErrors = { ...errors };
                delete nextErrors[item.id];
                return nextErrors;
              });
              setCurrentActiveItemId(item.id);
            }}
            onError={(event) => markMediaFailed(item.id, event.currentTarget)}
          >
            Your browser does not support video playback.
          </video>
          <div className="pointer-events-none absolute bottom-[calc(env(safe-area-inset-bottom)+2rem)] left-4 right-4 rounded bg-black/60 p-3">
            <h2 className="font-semibold">{item.title}</h2>
            {item.subtitle ? <p className="text-sm text-slate-200">{item.subtitle}</p> : null}
            {playbackErrors[item.id] ? (
              <p className="mt-1 text-sm text-amber-200" role="alert">This video could not be played.</p>
            ) : null}
            {renderActions ? <div className="pointer-events-auto mt-2">{renderActions(item)}</div> : null}
          </div>
        </section>
      ))}
      {footer}
    </main>
  );
}

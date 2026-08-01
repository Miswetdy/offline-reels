"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";

import {
  ReelsControls,
  ReelsSpeedIndicator,
  type ReelsSpeedIndicatorHandle,
} from "./vertical-video-feed/reels-controls";

export const REELS_EDGE_ZONE_FRACTION = 0.1;
export const REELS_HOLD_DELAY_MS = 250;
export const REELS_MOVEMENT_SLOP_PX = 12;
export const FULLSCREEN_COMMIT_RATIO = 0.999;
export const FULLSCREEN_COMMIT_TOLERANCE_PX = 2;
export const RESET_START_EPSILON_SECONDS = 0.05;

export type VerticalVideoFeedItem = {
  id: string;
  title: string;
  mediaUrl: string;
  subtitle?: ReactNode;
};

type VerticalVideoFeedProps = {
  items: VerticalVideoFeedItem[];
  controlsMode?: "native" | "reels";
  hasBottomNavigation?: boolean;
  emptyState?: ReactNode;
  footer?: ReactNode;
  renderActions?: (item: VerticalVideoFeedItem) => ReactNode;
  showMetadata?: boolean;
  onActiveItemChange?: (item: VerticalVideoFeedItem | null) => void;
};

type MediaMode = "previous" | "active" | "next" | "inactive";
type PlaybackErrorKind = "media" | "autoplay";
type StartPreparation = { pending: boolean; source: string | null; callbacks: Set<() => void> };
type ReelsGestureZone = "left-edge" | "center" | "right-edge";
type ReelsGesturePhase = "pending" | "center-hold" | "edge-hold";
type ReelsGestureCancellation = "active-item" | "lifecycle" | "movement" | "pointer" | "scroll";
type ReelsGesture = {
  itemId: string;
  video: HTMLVideoElement;
  pointerId: number;
  token: number;
  phase: ReelsGesturePhase;
  zone: ReelsGestureZone;
  startX: number;
  startY: number;
  timerId: number | null;
  wasPlaying: boolean;
  originalPlaybackRate: number;
};
type CenterHoldPause = {
  itemId: string;
  video: HTMLVideoElement;
  source: string | null;
  pointerId: number;
  token: number;
  wasPlaying: boolean;
  playbackGeneration: number;
};
type ProgressState = { itemId: string | null; value: number };
type PlaybackUiState = { itemId: string | null; paused: boolean };
type ReelsResumeRequest = { itemId: string; video: HTMLVideoElement; generation: number };
type CommittedDeparture = {
  generation: number;
  state: "required" | "in-flight" | "prepared";
  video?: HTMLVideoElement;
  source?: string | null;
  playbackGeneration?: number;
};

function isAutoplayPolicyError(error: unknown): boolean {
  return typeof error === "object"
    && error !== null
    && "name" in error
    && error.name === "NotAllowedError";
}

export function VerticalVideoFeed({
  items,
  controlsMode = "native",
  hasBottomNavigation = false,
  emptyState,
  footer,
  renderActions,
  showMetadata = true,
  onActiveItemChange,
}: VerticalVideoFeedProps) {
  const [activeItemId, setActiveItemId] = useState<string | null>(null);
  const [committedItemId, setCommittedItemId] = useState<string | null>(() => items[0]?.id ?? null);
  const [lastActiveIndex, setLastActiveIndex] = useState(0);
  // Reels intentionally enter with audible media. Native `/videos` retains its
  // existing muted-first behaviour and native controls.
  const [muted, setMuted] = useState(() => controlsMode !== "reels");
  const [playbackErrors, setPlaybackErrors] = useState<Record<string, PlaybackErrorKind>>({});
  const [reelsControlsItemId, setReelsControlsItemId] = useState<string | null>(null);
  const [playbackUi, setPlaybackUi] = useState<PlaybackUiState>({ itemId: null, paused: false });
  const [progress, setProgress] = useState<ProgressState>({ itemId: null, value: 0 });

  const feedRef = useRef<HTMLElement>(null);
  const itemRefs = useRef(new Map<string, HTMLElement>());
  const itemRefVersions = useRef(new Map<string, number>());
  const videoRefs = useRef(new Map<string, HTMLVideoElement>());
  const intersectionRatios = useRef(new Map<string, number>());
  const activeItemIdRef = useRef<string | null>(null);
  const playbackGenerationRef = useRef(0);
  const startPreparationsRef = useRef(new Map<HTMLVideoElement, StartPreparation>());
  const reelsGestureRef = useRef<ReelsGesture | null>(null);
  const centerHoldPauseRef = useRef<CenterHoldPause | null>(null);
  const reelsGestureTokenRef = useRef(0);
  const cancelReelsGestureRef = useRef<(_reason: ReelsGestureCancellation) => void>(() => undefined);
  const reelsResumeRequestRef = useRef<ReelsResumeRequest | null>(null);
  const reelsSpeedIndicatorRef = useRef<ReelsSpeedIndicatorHandle>(null);
  const committedItemIdRef = useRef<string | null>(items[0]?.id ?? null);
  const committedGenerationRef = useRef(0);
  const committedDeparturesRef = useRef(new Map<string, CommittedDeparture>());
  const prepareCommittedDepartureRef = useRef<(itemId: string, allowActivationFallback?: boolean) => void>(() => undefined);
  const commitFullscreenItemRef = useRef<(itemId: string) => void>(() => undefined);
  const activeItemStillExists = activeItemId !== null && items.some((item) => item.id === activeItemId);
  const fallbackActiveItemId = items[Math.min(lastActiveIndex, items.length - 1)]?.id ?? null;
  const effectiveActiveItemId = activeItemStillExists ? activeItemId : fallbackActiveItemId;
  const effectiveActiveMediaUrl = effectiveActiveItemId === null
    ? null
    : items.find((item) => item.id === effectiveActiveItemId)?.mediaUrl ?? null;
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
    if (activeItemIdRef.current !== itemId) {
      cancelReelsGestureRef.current("active-item");
      setReelsControlsItemId(null);
      reelsResumeRequestRef.current = null;
    }
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

  const isEffectivelyFullscreen = useCallback((element: Element, ratio: number) => {
    if (ratio < FULLSCREEN_COMMIT_RATIO) return false;
    const root = feedRef.current;
    if (root === null) return false;
    const rootRect = root.getBoundingClientRect();
    const itemRect = element.getBoundingClientRect();
    // JSDOM and a few embedded WebKit contexts can expose zero geometry. In a
    // real feed, require both edges to align within a small rounding tolerance.
    if (rootRect.height <= 0 || itemRect.height <= 0) return true;
    const rootBottom = rootRect.top + rootRect.height;
    const itemBottom = itemRect.top + itemRect.height;
    return Math.abs(itemRect.top - rootRect.top) <= FULLSCREEN_COMMIT_TOLERANCE_PX
      && Math.abs(itemBottom - rootBottom) <= FULLSCREEN_COMMIT_TOLERANCE_PX;
  }, []);

  const isEffectivelyOffscreen = useCallback((element: Element) => {
    const root = feedRef.current;
    if (root === null) return false;
    const rootRect = root.getBoundingClientRect();
    const itemRect = element.getBoundingClientRect();
    if (rootRect.height <= 0 || itemRect.height <= 0) return true;
    const rootBottom = rootRect.top + rootRect.height;
    const itemBottom = itemRect.top + itemRect.height;
    return itemBottom <= rootRect.top + FULLSCREEN_COMMIT_TOLERANCE_PX
      || itemRect.top >= rootBottom - FULLSCREEN_COMMIT_TOLERANCE_PX;
  }, []);

  const hasMeasurableFeedGeometry = useCallback((element: Element) => {
    const root = feedRef.current;
    if (root === null) return false;
    return root.getBoundingClientRect().height > 0 && element.getBoundingClientRect().height > 0;
  }, []);

  const currentIntersectionRatio = useCallback((element: Element, reportedRatio: number) => {
    const root = feedRef.current;
    if (root === null) return reportedRatio;
    const rootRect = root.getBoundingClientRect();
    const itemRect = element.getBoundingClientRect();
    if (rootRect.height <= 0 || itemRect.height <= 0) return reportedRatio;
    const rootBottom = rootRect.top + rootRect.height;
    const itemBottom = itemRect.top + itemRect.height;
    const visibleHeight = Math.max(0, Math.min(itemBottom, rootBottom) - Math.max(itemRect.top, rootRect.top));
    return Math.min(1, visibleHeight / itemRect.height);
  }, []);

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
        committedDeparturesRef.current.delete(itemId);
      }
    }
    for (const itemId of itemIds) {
      if (!intersectionRatios.current.has(itemId)) intersectionRatios.current.set(itemId, 0);
    }
    if (committedItemIdRef.current !== null && !itemIds.has(committedItemIdRef.current)) {
      const replacementCommittedItemId = items[0]?.id ?? null;
      committedItemIdRef.current = replacementCommittedItemId;
      setCommittedItemId(replacementCommittedItemId);
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const fullyOffscreenItemIds: string[] = [];
        const fullscreenItemIds: string[] = [];
        for (const entry of entries) {
          const itemId = (entry.target as HTMLElement).dataset.videoId;
          if (!itemId) continue;
          const reportedRatio = entry.isIntersecting ? entry.intersectionRatio : 0;
          const ratio = currentIntersectionRatio(entry.target, reportedRatio);
          intersectionRatios.current.set(itemId, ratio);
          // An outgoing card can still be visible when the next item becomes
          // active. Keep its final rendered frame until it is fully outside the
          // feed, then prepare the first frame for a future return.
          if (ratio === 0) fullyOffscreenItemIds.push(itemId);
          if (reportedRatio >= FULLSCREEN_COMMIT_RATIO && isEffectivelyFullscreen(entry.target, ratio)) {
            fullscreenItemIds.push(itemId);
          }
        }
        selectActiveItemFromRatios();
        for (const itemId of fullscreenItemIds) commitFullscreenItemRef.current(itemId);
        for (const itemId of fullyOffscreenItemIds) {
          if (activeItemIdRef.current !== itemId) prepareCommittedDepartureRef.current(itemId);
        }
      },
      { root, threshold: [0, 0.25, 0.5, 0.75, 1] },
    );
    itemRefs.current.forEach((item) => observer.observe(item));
    if (activeItemIdRef.current === null) setCurrentActiveItemId(items[0].id);
    return () => observer.disconnect();
  }, [currentIntersectionRatio, isEffectivelyFullscreen, items, selectActiveItemFromRatios, setCurrentActiveItemId]);

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

  const prepareVideoForStart = useCallback((video: HTMLVideoElement, onPrepared?: () => void) => {
    const existingPreparation = startPreparationsRef.current.get(video);
    if (existingPreparation?.pending) {
      if (onPrepared) existingPreparation.callbacks.add(onPrepared);
      return;
    }

    const preparation: StartPreparation = {
      pending: true,
      source: video.getAttribute("src"),
      callbacks: new Set(),
    };
    if (onPrepared) preparation.callbacks.add(onPrepared);
    startPreparationsRef.current.set(video, preparation);
    video.pause();
    video.style.visibility = "hidden";

    const isCurrentPreparation = () => (
      startPreparationsRef.current.get(video) === preparation
      && video.getAttribute("src") === preparation.source
      && preparation.pending
    );

    const finishPreparation = () => {
      if (!isCurrentPreparation()) return;
      preparation.pending = false;
      video.style.visibility = "";
      for (const callback of preparation.callbacks) callback();
      preparation.callbacks.clear();
    };

    const finishWhenFrameReady = (frameReady = false) => {
      if (!isCurrentPreparation()) return;
      if (Math.abs(video.currentTime) > RESET_START_EPSILON_SECONDS) return;
      if (frameReady || video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
        finishPreparation();
        return;
      }
      video.addEventListener("loadeddata", () => finishWhenFrameReady(true), { once: true });
      video.addEventListener("canplay", () => finishWhenFrameReady(true), { once: true });
    };

    if (Math.abs(video.currentTime) <= RESET_START_EPSILON_SECONDS) {
      finishWhenFrameReady();
    } else {
      video.addEventListener("seeked", () => finishWhenFrameReady(false), { once: true });
      video.currentTime = 0;
    }
  }, []);

  const prepareCommittedDeparture = useCallback((itemId: string, allowActivationFallback = false) => {
    const departure = committedDeparturesRef.current.get(itemId);
    const item = itemRefs.current.get(itemId);
    if (!departure || !item || (activeItemIdRef.current === itemId && !allowActivationFallback)) return;
    const ratio = intersectionRatios.current.get(itemId) ?? 0;
    if (
      !allowActivationFallback
      && (!isEffectivelyOffscreen(item) || (!hasMeasurableFeedGeometry(item) && ratio !== 0))
    ) return;
    const video = videoRefs.current.get(itemId);
    if (!video || !video.hasAttribute("src")) return;
    if (
      departure.state === "prepared"
      && departure.video === video
      && departure.source === video.getAttribute("src")
      && Math.abs(video.currentTime) <= RESET_START_EPSILON_SECONDS
    ) return;
    const source = video.getAttribute("src");
    const generation = departure.generation;
    const playbackGeneration = playbackGenerationRef.current;
    if (departure.state === "in-flight" && departure.video === video && departure.source === source) return;
    committedDeparturesRef.current.set(itemId, {
      generation,
      state: "in-flight",
      video,
      source,
      playbackGeneration,
    });
    prepareVideoForStart(video, () => {
      const currentDeparture = committedDeparturesRef.current.get(itemId);
      if (
        currentDeparture?.generation === generation
        && currentDeparture.state === "in-flight"
        && currentDeparture.playbackGeneration === playbackGeneration
        && videoRefs.current.get(itemId) === video
        && video.getAttribute("src") === source
        && Math.abs(video.currentTime) <= RESET_START_EPSILON_SECONDS
      ) {
        committedDeparturesRef.current.set(itemId, {
          generation,
          state: "prepared",
          video,
          source,
          playbackGeneration,
        });
      }
    });
  }, [hasMeasurableFeedGeometry, isEffectivelyOffscreen, prepareVideoForStart]);

  const commitFullscreenItem = useCallback((itemId: string) => {
    if (activeItemIdRef.current !== itemId || committedItemIdRef.current === itemId) return;
    const previousCommittedItemId = committedItemIdRef.current;
    committedItemIdRef.current = itemId;
    setCommittedItemId(itemId);
    committedDeparturesRef.current.delete(itemId);
    const generation = ++committedGenerationRef.current;
    if (previousCommittedItemId !== null && previousCommittedItemId !== itemId) {
      committedDeparturesRef.current.set(previousCommittedItemId, { generation, state: "required" });
      // Commit and initial background preparation are one operation. This
      // closes the A=0 → B=full callback-order race: cached geometry/ratio is
      // inspected immediately instead of waiting for another A callback.
      prepareCommittedDeparture(previousCommittedItemId);
    }
  }, [prepareCommittedDeparture]);

  useLayoutEffect(() => {
    prepareCommittedDepartureRef.current = prepareCommittedDeparture;
    commitFullscreenItemRef.current = commitFullscreenItem;
  }, [commitFullscreenItem, prepareCommittedDeparture]);

  const cancelStartPreparation = useCallback((video: HTMLVideoElement) => {
    startPreparationsRef.current.delete(video);
    video.style.visibility = "";
  }, []);

  const clearVideoSource = useCallback((video: HTMLVideoElement) => {
    cancelStartPreparation(video);
    if (video.hasAttribute("src")) {
      video.pause();
      video.removeAttribute("src");
      video.load();
    }
  }, [cancelStartPreparation]);

  const markMediaFailed = useCallback((itemId: string, video: HTMLVideoElement) => {
    const expectedSource = items.find((item) => item.id === itemId)?.mediaUrl;
    if (
      activeItemIdRef.current !== itemId
      || videoRefs.current.get(itemId) !== video
      || expectedSource === undefined
      || video.getAttribute("src") !== expectedSource
    ) return;
    playbackGenerationRef.current += 1;
    clearVideoSource(video);
    setPlaybackErrors((errors) => errors[itemId] === "media" ? errors : { ...errors, [itemId]: "media" });
  }, [clearVideoSource, items]);

  const pauseAllVideos = useCallback(() => {
    playbackGenerationRef.current += 1;
    videoRefs.current.forEach((video) => video.pause());
  }, []);

  const playCurrentVideo = useCallback((itemId: string, video: HTMLVideoElement, isTapResume = false) => {
    if (activeItemIdRef.current !== itemId || videoRefs.current.get(itemId) !== video) return;
    const generation = ++playbackGenerationRef.current;
    if (isTapResume) reelsResumeRequestRef.current = { itemId, video, generation };
    videoRefs.current.forEach((candidate, candidateId) => {
      if (candidateId !== itemId) candidate.pause();
    });
    void video.play().then(
      () => {
        if (
          generation !== playbackGenerationRef.current
          || activeItemIdRef.current !== itemId
          || videoRefs.current.get(itemId) !== video
        ) {
          if (reelsResumeRequestRef.current?.generation === generation) reelsResumeRequestRef.current = null;
          video.pause();
        }
      },
      () => {
        if (
          generation === playbackGenerationRef.current
          && activeItemIdRef.current === itemId
          && videoRefs.current.get(itemId) === video
        ) {
          if (reelsResumeRequestRef.current?.generation === generation) reelsResumeRequestRef.current = null;
          setPlaybackErrors((errors) => ({ ...errors, [itemId]: "autoplay" }));
          setPlaybackUi({ itemId, paused: true });
        }
      },
    );
  }, []);

  const releaseCenterHoldPause = useCallback((pointerId: number | null, allowResume: boolean) => {
    const centerHoldPause = centerHoldPauseRef.current;
    if (!centerHoldPause || (pointerId !== null && centerHoldPause.pointerId !== pointerId)) return;
    centerHoldPauseRef.current = null;
    if (
      !allowResume
      || !centerHoldPause.wasPlaying
      || document.visibilityState === "hidden"
      || activeItemIdRef.current !== centerHoldPause.itemId
      || videoRefs.current.get(centerHoldPause.itemId) !== centerHoldPause.video
      || centerHoldPause.video.getAttribute("src") !== centerHoldPause.source
      || playbackGenerationRef.current !== centerHoldPause.playbackGeneration
    ) return;
    playCurrentVideo(centerHoldPause.itemId, centerHoldPause.video);
  }, [playCurrentVideo]);

  const finishReelsGesture = useCallback(() => {
    const gesture = reelsGestureRef.current;
    reelsGestureTokenRef.current += 1;
    reelsGestureRef.current = null;
    if (!gesture) return;
    if (gesture.timerId !== null) window.clearTimeout(gesture.timerId);
    if (gesture.phase === "edge-hold") {
      gesture.video.playbackRate = gesture.originalPlaybackRate;
      reelsSpeedIndicatorRef.current?.hide();
      return;
    }
  }, []);

  const cancelReelsGesture = useCallback((reason: ReelsGestureCancellation) => {
    finishReelsGesture();
    if (reason === "lifecycle") releaseCenterHoldPause(null, false);
    reelsResumeRequestRef.current = null;
    reelsSpeedIndicatorRef.current?.hide();
    setReelsControlsItemId(null);
  }, [finishReelsGesture, releaseCenterHoldPause]);

  const toggleCurrentVideo = useCallback((itemId: string, video: HTMLVideoElement) => {
    if (activeItemIdRef.current !== itemId || videoRefs.current.get(itemId) !== video) return;
    setReelsControlsItemId(itemId);
    if (video.paused) {
      playCurrentVideo(itemId, video, true);
      return;
    }
    reelsResumeRequestRef.current = null;
    playbackGenerationRef.current += 1;
    video.pause();
    setPlaybackUi({ itemId, paused: true });
  }, [playCurrentVideo]);

  const updateActiveProgress = useCallback((itemId: string, video: HTMLVideoElement) => {
    if (controlsMode !== "reels" || activeItemIdRef.current !== itemId) return;
    const duration = video.duration;
    const currentTime = video.currentTime;
    const value = Number.isFinite(duration) && duration > 0 && Number.isFinite(currentTime)
      ? Math.min(1, Math.max(0, currentTime / duration))
      : 0;
    setProgress((current) => current.itemId === itemId && current.value === value
      ? current
      : { itemId, value });
  }, [controlsMode]);

  const handleReelsPointerDown = useCallback((
    event: ReactPointerEvent<HTMLDivElement>,
    itemId: string,
  ) => {
    if (
      controlsMode !== "reels"
      || !event.isPrimary
      || event.button !== 0
      || activeItemIdRef.current !== itemId
    ) return;
    finishReelsGesture();
    // A new primary touch is a reliable boundary for any old sequence that
    // failed to report its end. Never autoplay the old held item here.
    releaseCenterHoldPause(null, false);
    const video = videoRefs.current.get(itemId);
    if (!video) return;

    const bounds = event.currentTarget.getBoundingClientRect();
    const horizontalPosition = bounds.width > 0 ? (event.clientX - bounds.left) / bounds.width : 0.5;
    const zone: ReelsGestureZone = horizontalPosition <= REELS_EDGE_ZONE_FRACTION
      ? "left-edge"
      : horizontalPosition >= 1 - REELS_EDGE_ZONE_FRACTION
        ? "right-edge"
        : "center";
    const token = ++reelsGestureTokenRef.current;
    const gesture: ReelsGesture = {
      itemId,
      video,
      pointerId: event.pointerId,
      token,
      phase: "pending",
      zone,
      startX: event.clientX,
      startY: event.clientY,
      timerId: null,
      wasPlaying: false,
      originalPlaybackRate: video.playbackRate,
    };
    gesture.timerId = window.setTimeout(() => {
      if (
        reelsGestureRef.current !== gesture
        || reelsGestureTokenRef.current !== token
        || activeItemIdRef.current !== itemId
        || videoRefs.current.get(itemId) !== video
      ) {
        finishReelsGesture();
        return;
      }
      gesture.timerId = null;
      if (gesture.zone === "center") {
        gesture.phase = "center-hold";
        gesture.wasPlaying = !video.paused;
        const playbackGeneration = ++playbackGenerationRef.current;
        centerHoldPauseRef.current = {
          itemId,
          video,
          source: video.getAttribute("src"),
          pointerId: event.pointerId,
          token,
          wasPlaying: gesture.wasPlaying,
          playbackGeneration,
        };
        if (gesture.wasPlaying) video.pause();
        return;
      }
      gesture.phase = "edge-hold";
      gesture.originalPlaybackRate = video.playbackRate;
      video.playbackRate = 2;
      reelsSpeedIndicatorRef.current?.show(itemId, gesture.zone);
    }, REELS_HOLD_DELAY_MS);
    reelsGestureRef.current = gesture;
  }, [controlsMode, finishReelsGesture, releaseCenterHoldPause]);

  const handleReelsPointerMove = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const gesture = reelsGestureRef.current;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    const distance = Math.hypot(event.clientX - gesture.startX, event.clientY - gesture.startY);
    if (distance <= REELS_MOVEMENT_SLOP_PX) return;
    cancelReelsGesture("movement");
  }, [cancelReelsGesture]);

  const handleReelsPointerUp = useCallback((
    event: ReactPointerEvent<HTMLDivElement>,
    itemId: string,
  ) => {
    const gesture = reelsGestureRef.current;
    if (!gesture || gesture.pointerId !== event.pointerId || gesture.itemId !== itemId) {
      releaseCenterHoldPause(event.pointerId, true);
      return;
    }
    if (gesture.phase === "pending") {
      const video = gesture.video;
      finishReelsGesture();
      toggleCurrentVideo(itemId, video);
      return;
    }
    const isCenterHold = gesture.phase === "center-hold";
    finishReelsGesture();
    if (isCenterHold) releaseCenterHoldPause(event.pointerId, true);
  }, [finishReelsGesture, releaseCenterHoldPause, toggleCurrentVideo]);

  const handleReelsPointerCancellation = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    const gesture = reelsGestureRef.current;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    cancelReelsGesture("pointer");
  }, [cancelReelsGesture]);

  useEffect(() => {
    cancelReelsGestureRef.current = cancelReelsGesture;
    return () => {
      cancelReelsGestureRef.current = () => undefined;
    };
  }, [cancelReelsGesture]);

  useEffect(() => {
    const releaseFromPointerUp = (event: PointerEvent) => releaseCenterHoldPause(event.pointerId, true);
    const releaseFromTouchEnd = (event: TouchEvent) => {
      if (event.touches.length === 0) releaseCenterHoldPause(null, true);
    };
    const clearFromTouchCancel = (event: TouchEvent) => {
      if (event.touches.length === 0) releaseCenterHoldPause(null, false);
    };

    document.addEventListener("pointerup", releaseFromPointerUp);
    document.addEventListener("touchend", releaseFromTouchEnd);
    document.addEventListener("touchcancel", clearFromTouchCancel);
    return () => {
      document.removeEventListener("pointerup", releaseFromPointerUp);
      document.removeEventListener("touchend", releaseFromTouchEnd);
      document.removeEventListener("touchcancel", clearFromTouchCancel);
    };
  }, [releaseCenterHoldPause]);

  useEffect(() => {
    const pauseForBackground = () => {
      cancelReelsGesture("lifecycle");
      pauseAllVideos();
    };
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
  }, [cancelReelsGesture, pauseAllVideos]);

  useEffect(() => () => {
    cancelReelsGesture("lifecycle");
    pauseAllVideos();
    startPreparationsRef.current.clear();
    videoRefs.current.forEach(clearVideoSource);
  }, [cancelReelsGesture, clearVideoSource, pauseAllVideos]);

  useEffect(() => {
    const mountedVideos = new Set(videoRefs.current.values());
    for (const video of startPreparationsRef.current.keys()) {
      if (!mountedVideos.has(video)) startPreparationsRef.current.delete(video);
    }
  }, [items]);

  useEffect(() => {
    const desiredItems = items.filter((item) => sourceMode(item.id) !== "inactive");

    videoRefs.current.forEach((video, itemId) => {
      const item = items.find((candidate) => candidate.id === itemId);
      if (!item) return;
      const mode = sourceMode(itemId);
      video.muted = muted;
      video.preload = mode === "active" ? "auto" : mode === "inactive" ? "none" : "metadata";
      if (mode === "inactive") {
        committedDeparturesRef.current.delete(itemId);
        clearVideoSource(video);
      }
    });

    desiredItems.forEach((item) => {
      const video = videoRefs.current.get(item.id);
      if (video && video.getAttribute("src") !== item.mediaUrl) {
        committedDeparturesRef.current.delete(item.id);
        cancelStartPreparation(video);
        video.src = item.mediaUrl;
        video.load();
      }
    });
  }, [cancelStartPreparation, clearVideoSource, items, muted, sourceMode]);

  useEffect(() => {
    const activeVideo = effectiveActiveItemId ? videoRefs.current.get(effectiveActiveItemId) : undefined;
    const generation = ++playbackGenerationRef.current;
    videoRefs.current.forEach((video, itemId) => {
      if (itemId !== effectiveActiveItemId) video.pause();
    });
    if (!activeVideo || !effectiveActiveItemId) return;

    const centerHoldPause = centerHoldPauseRef.current;
    if (centerHoldPause?.itemId === effectiveActiveItemId) {
      if (
        centerHoldPause.video === activeVideo
        && centerHoldPause.source === activeVideo.getAttribute("src")
      ) {
        // A centre hold remains scoped to its original item while the same
        // physical touch continues. Another active item is not blocked, but
        // a partial-scroll reversal must not autoplay this held item.
        centerHoldPause.playbackGeneration = generation;
        activeVideo.pause();
        return;
      }
      // A source or DOM replacement invalidates the old physical hold.
      centerHoldPauseRef.current = null;
    }

    const isSameActiveVideo = () => (
      activeItemIdRef.current === effectiveActiveItemId
      && videoRefs.current.get(effectiveActiveItemId) === activeVideo
      && activeVideo.getAttribute("src") === effectiveActiveMediaUrl
    );
    const isCurrentActiveVideo = () => (
      generation === playbackGenerationRef.current
      && isSameActiveVideo()
    );
    let startupPlayAttempted = false;
    const startActivePlayback = () => {
      if (!isCurrentActiveVideo() || startupPlayAttempted) return;
      startupPlayAttempted = true;
      void activeVideo.play().then(
        () => {
          if (!isCurrentActiveVideo() && !isSameActiveVideo()) activeVideo.pause();
        },
        (error: unknown) => {
          if (isCurrentActiveVideo()) {
            setPlaybackErrors((errors) => ({ ...errors, [effectiveActiveItemId]: "autoplay" }));
            // iOS can reject an audible startup before the first user gesture.
            // Do not silently fall back to muted playback: leave the requested
            // sound state intact and expose the same explicit Play control.
            if (controlsMode === "reels" && isAutoplayPolicyError(error)) {
              setPlaybackUi({ itemId: effectiveActiveItemId, paused: true });
              setReelsControlsItemId(effectiveActiveItemId);
            }
          }
        },
      );
    };

    const departure = committedDeparturesRef.current.get(effectiveActiveItemId);
    const isPreparedAtZero = departure?.state === "prepared"
      && departure.video === activeVideo
      && departure.source === activeVideo.getAttribute("src")
      && Math.abs(activeVideo.currentTime) <= RESET_START_EPSILON_SECONDS;
    // Crossing the active threshold is reversible while a drag is in flight.
    // A prepared committed-away item is already on its first decoded frame and
    // must play directly; only required/in-flight departures use the fallback.
    let resetBeforePlay = (!isPreparedAtZero && departure !== undefined)
      || startPreparationsRef.current.get(activeVideo)?.pending === true;
    const playActiveVideo = () => {
      if (!isCurrentActiveVideo()) return;
      if (!resetBeforePlay) {
        startActivePlayback();
        return;
      }
      resetBeforePlay = false;
      if (departure !== undefined && !isPreparedAtZero) {
        prepareCommittedDepartureRef.current(effectiveActiveItemId, true);
      }
      prepareVideoForStart(activeVideo, startActivePlayback);
    };

    const startAfterLoadedMetadata = playActiveVideo;
    let waitingForMetadata = false;
    if (activeVideo.readyState >= HTMLMediaElement.HAVE_METADATA) {
      playActiveVideo();
    } else {
      waitingForMetadata = true;
      activeVideo.addEventListener("loadedmetadata", startAfterLoadedMetadata, { once: true });
    }
    return () => {
      if (generation === playbackGenerationRef.current) playbackGenerationRef.current += 1;
      if (waitingForMetadata) activeVideo.removeEventListener("loadedmetadata", startAfterLoadedMetadata);
    };
  }, [controlsMode, effectiveActiveItemId, effectiveActiveMediaUrl, prepareVideoForStart]);

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

  const setVideoRef = useCallback((itemId: string, element: HTMLVideoElement | null) => {
    if (element) videoRefs.current.set(itemId, element);
    else videoRefs.current.delete(itemId);
  }, []);

  const videoRefCallbacks = useMemo(
    () => new Map(items.map((item) => [item.id, (element: HTMLVideoElement | null) => setVideoRef(item.id, element)])),
    [items, setVideoRef],
  );

  if (items.length === 0) {
    return <>{emptyState ?? <main className="grid h-dvh place-items-center p-6">No videos are available yet.</main>}</>;
  }

  return (
    <main
      ref={feedRef}
      className="relative h-dvh snap-y snap-mandatory overflow-y-auto bg-slate-950 text-white"
      aria-label="Video feed"
      data-committed-item-id={committedItemId ?? undefined}
      onScroll={controlsMode === "reels" ? () => cancelReelsGesture("scroll") : undefined}
    >
      {controlsMode === "native" ? (
        <button
          className="fixed right-4 top-[calc(env(safe-area-inset-top)+1rem)] z-10 rounded-full bg-black/70 px-4 py-2 text-sm font-medium text-white focus:outline-2 focus:outline-offset-2 focus:outline-white"
          type="button"
          aria-label={muted ? "Turn sound on" : "Mute videos"}
          aria-pressed={!muted}
          onClick={() => setMuted((value) => !value)}
        >
          {muted ? "Unmute" : "Mute"}
        </button>
      ) : null}
      {items.map((item) => {
        const mode = sourceMode(item.id);
        const isActive = item.id === effectiveActiveItemId;
        const isActivePaused = playbackUi.itemId === item.id && playbackUi.paused;
        const showReelsControls = controlsMode === "reels" && isActive && reelsControlsItemId === item.id;
        const progressValue = progress.itemId === item.id ? progress.value : 0;
        const hasTerminalMediaError = playbackErrors[item.id] === "media";

        return (
          <section
            key={item.id}
            ref={(element) => setItemRef(item.id, element)}
            data-video-id={item.id}
            className={`relative flex h-dvh snap-start snap-always items-center justify-center bg-black${
              controlsMode === "reels" ? " reels-interaction-card" : ""
            }`}
            aria-label={item.title}
            onContextMenu={controlsMode === "reels" ? (event) => event.preventDefault() : undefined}
          >
            <video
              ref={videoRefCallbacks.get(item.id)}
              className={controlsMode === "reels"
                ? "h-full w-full object-cover"
                : hasBottomNavigation
                  ? "h-[calc(100%-var(--app-bottom-navigation-space))] w-full self-start object-contain"
                  : "h-full w-full object-contain"}
              controls={controlsMode === "native"}
              loop={controlsMode === "reels"}
              draggable={controlsMode === "reels" ? false : undefined}
              onDragStart={controlsMode === "reels" ? (event) => event.preventDefault() : undefined}
              muted={muted}
              playsInline
              preload={mode === "active" ? "auto" : mode === "inactive" ? "none" : "metadata"}
              aria-busy={mode !== "inactive" && !hasTerminalMediaError}
              onPlay={(event) => {
                const video = event.currentTarget;
                if (
                  controlsMode === "reels"
                  && (
                    activeItemIdRef.current !== item.id
                    || videoRefs.current.get(item.id) !== video
                    || video.getAttribute("src") !== item.mediaUrl
                  )
                ) return;
                setPlaybackErrors((errors) => {
                  if (errors[item.id] === undefined) return errors;
                  const nextErrors = { ...errors };
                  delete nextErrors[item.id];
                  return nextErrors;
                });
                const resumeRequest = reelsResumeRequestRef.current;
                if (controlsMode === "native") {
                  setCurrentActiveItemId(item.id);
                  if (activeItemIdRef.current === item.id) setPlaybackUi({ itemId: item.id, paused: false });
                }
                if (
                  controlsMode === "reels"
                  && activeItemIdRef.current === item.id
                  && resumeRequest?.itemId === item.id
                  && resumeRequest.video === video
                  && resumeRequest.generation === playbackGenerationRef.current
                ) {
                  reelsResumeRequestRef.current = null;
                  setPlaybackUi({ itemId: item.id, paused: false });
                  setReelsControlsItemId((current) => current === item.id ? null : current);
                }
              }}
              onPause={(event) => {
                if (activeItemIdRef.current === item.id) {
                  if (reelsResumeRequestRef.current?.video === event.currentTarget) {
                    reelsResumeRequestRef.current = null;
                  }
                  setPlaybackUi({ itemId: item.id, paused: true });
                }
              }}
              onSeeked={(event) => {
                updateActiveProgress(item.id, event.currentTarget);
              }}
              onTimeUpdate={(event) => {
                updateActiveProgress(item.id, event.currentTarget);
              }}
              onDurationChange={(event) => updateActiveProgress(item.id, event.currentTarget)}
              onLoadedMetadata={(event) => {
                updateActiveProgress(item.id, event.currentTarget);
              }}
              onError={(event) => {
                markMediaFailed(item.id, event.currentTarget);
              }}
            >
              Your browser does not support video playback.
            </video>
            {controlsMode === "reels" && isActive ? (
              <>
                <div
                  className="reels-gesture-surface absolute inset-0 z-[1]"
                  data-testid={`reels-gesture-${item.id}`}
                  aria-hidden="true"
                  onPointerDown={(event) => handleReelsPointerDown(event, item.id)}
                  onPointerMove={handleReelsPointerMove}
                  onPointerUp={(event) => handleReelsPointerUp(event, item.id)}
                  onPointerCancel={handleReelsPointerCancellation}
                  onLostPointerCapture={handleReelsPointerCancellation}
                />
                <ReelsControls
                  itemId={item.id}
                  visible={showReelsControls}
                  muted={muted}
                  paused={isActivePaused}
                  onToggleMuted={() => {
                    setMuted((value) => !value);
                    setReelsControlsItemId(item.id);
                  }}
                  onTogglePlayback={() => {
                    const video = videoRefs.current.get(item.id);
                    if (video) toggleCurrentVideo(item.id, video);
                  }}
                />
                <ReelsSpeedIndicator ref={reelsSpeedIndicatorRef} />
              </>
            ) : null}
            {controlsMode === "reels" ? (
              isActive ? (
                <div className="reels-bottom-layout" data-testid={`reels-bottom-layout-${item.id}`}>
                  {showMetadata || hasTerminalMediaError || renderActions ? (
                    <div className="reels-metadata-overlay" data-testid={`reels-metadata-${item.id}`}>
                      {showMetadata ? <h2 className="font-semibold">{item.title}</h2> : null}
                      {showMetadata && item.subtitle ? <p className="text-sm text-slate-200">{item.subtitle}</p> : null}
                      {hasTerminalMediaError ? (
                        <p className="mt-1 text-sm text-amber-200" role="alert">Не удалось воспроизвести видео.</p>
                      ) : null}
                      {renderActions ? <div className="pointer-events-auto mt-2">{renderActions(item)}</div> : null}
                    </div>
                  ) : null}
                  <div className="reels-progress-glass-zone pointer-events-none" data-testid={`reels-progress-glass-${item.id}`}>
                    <div
                      className="reels-progress h-0.5 overflow-hidden rounded-full bg-white/30"
                      data-testid={`reels-progress-${item.id}`}
                      role="progressbar"
                      aria-label="Прогресс видео"
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={Math.round(progressValue * 100)}
                    >
                      <span
                        className="block h-full origin-left bg-white transition-transform duration-100 motion-reduce:transition-none"
                        style={{ transform: `scaleX(${progressValue})` }}
                      />
                    </div>
                  </div>
                </div>
              ) : null
            ) : (
              <div className={`pointer-events-none absolute left-4 right-4 z-10 rounded bg-black/60 p-3${
                hasBottomNavigation ? " bottom-[var(--app-bottom-navigation-space)]" : " bottom-[calc(env(safe-area-inset-bottom)+2rem)]"
              }`}>
                <h2 className="font-semibold">{item.title}</h2>
                {item.subtitle ? <p className="text-sm text-slate-200">{item.subtitle}</p> : null}
                {hasTerminalMediaError ? (
                  <p className="mt-1 text-sm text-amber-200" role="alert">Не удалось воспроизвести видео.</p>
                ) : null}
                {renderActions ? <div className="pointer-events-auto mt-2">{renderActions(item)}</div> : null}
              </div>
            )}
          </section>
        );
      })}
      {footer}
    </main>
  );
}

"use client";

import {
  forwardRef,
  useImperativeHandle,
  useState,
} from "react";

export type ReelsSpeedIndicatorHandle = {
  show: (itemId: string, zone: "left-edge" | "right-edge") => void;
  hide: () => void;
};

type ReelsSpeedIndicatorState = {
  itemId: string;
  zone: "left-edge" | "right-edge";
};

type ReelsControlsProps = {
  itemId: string;
  visible: boolean;
  muted: boolean;
  paused: boolean;
  onToggleMuted: () => void;
  onTogglePlayback: () => void;
};

export const ReelsSpeedIndicator = forwardRef<ReelsSpeedIndicatorHandle>(function ReelsSpeedIndicator(_props, ref) {
  const [indicator, setIndicator] = useState<ReelsSpeedIndicatorState | null>(null);

  useImperativeHandle(ref, () => ({
    show: (itemId, zone) => setIndicator({ itemId, zone }),
    hide: () => setIndicator(null),
  }), []);

  if (indicator === null) return null;

  return (
    <div
      className={`pointer-events-none absolute top-1/2 z-30 -translate-y-1/2 rounded-full bg-black/70 px-3 py-2 text-sm font-semibold ${
        indicator.zone === "left-edge"
          ? "left-[calc(env(safe-area-inset-left)+1rem)]"
          : "right-[calc(env(safe-area-inset-right)+1rem)]"
      }`}
      data-testid={`reels-speed-${indicator.zone}`}
      data-video-id={indicator.itemId}
      aria-hidden="true"
    >
      2×
    </div>
  );
});

function PlayIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-9 w-9" fill="currentColor" aria-hidden="true">
      <path d="M8 5.2c0-1.02 1.13-1.64 2-1.1l8.13 5.02a3.4 3.4 0 0 1 0 5.76L10 19.9c-.87.54-2-.08-2-1.1V5.2Z" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-8 w-8" fill="currentColor" aria-hidden="true">
      <path d="M7 5.5A1.5 1.5 0 0 1 8.5 4h1A1.5 1.5 0 0 1 11 5.5v13A1.5 1.5 0 0 1 9.5 20h-1A1.5 1.5 0 0 1 7 18.5v-13Zm6 0A1.5 1.5 0 0 1 14.5 4h1A1.5 1.5 0 0 1 17 5.5v13a1.5 1.5 0 0 1-1.5 1.5h-1a1.5 1.5 0 0 1-1.5-1.5v-13Z" />
    </svg>
  );
}

function SpeakerIcon({ muted }: { muted: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 10h3.5L12 6v12l-4.5-4H4v-4Z" fill="currentColor" stroke="currentColor" />
      {muted ? (
        <path d="m16 9 4 4m0-4-4 4" />
      ) : (
        <>
          <path d="M15.5 9.2a4 4 0 0 1 0 5.6" />
          <path d="M18.2 6.5a7.8 7.8 0 0 1 0 11" />
        </>
      )}
    </svg>
  );
}

export function ReelsControls({
  itemId,
  visible,
  muted,
  paused,
  onToggleMuted,
  onTogglePlayback,
}: ReelsControlsProps) {
  return (
    <div
      className={`pointer-events-none absolute inset-x-0 top-1/2 z-30 flex -translate-y-1/2 flex-col items-center gap-3 transition-opacity duration-150 motion-reduce:transition-none ${
        visible ? "opacity-100" : "opacity-0"
      }`}
      data-testid={`reels-controls-${itemId}`}
      aria-hidden={!visible}
    >
      <button
        className={`pointer-events-auto grid h-11 w-11 place-items-center rounded-full bg-black/65 text-xl text-white shadow focus:outline-2 focus:outline-offset-2 focus:outline-white ${
          visible ? "" : "pointer-events-none"
        }`}
        type="button"
        tabIndex={visible ? 0 : -1}
        aria-label={muted ? "Включить звук" : "Выключить звук"}
        aria-pressed={!muted}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={(event) => {
          event.stopPropagation();
          onToggleMuted();
        }}
      >
        <SpeakerIcon muted={muted} />
      </button>
      <button
        className={`pointer-events-auto grid h-20 w-20 place-items-center rounded-full bg-black/65 text-3xl text-white shadow focus:outline-2 focus:outline-offset-2 focus:outline-white ${
          visible ? "" : "pointer-events-none"
        }`}
        type="button"
        tabIndex={visible ? 0 : -1}
        aria-label={paused ? "Воспроизвести видео" : "Приостановить видео"}
        aria-pressed={!paused}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={(event) => {
          event.stopPropagation();
          onTogglePlayback();
        }}
      >
        {paused ? <PlayIcon /> : <PauseIcon />}
      </button>
    </div>
  );
}

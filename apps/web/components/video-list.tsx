"use client";

import { useEffect, useState } from "react";

import { getVideoStreamUrl, getVideos, type Video } from "../lib/api/videos";

type VideosState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "success"; videos: Video[] };

export function VideoList() {
  const [state, setState] = useState<VideosState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    getVideos().then(
      (videos) => active && setState({ status: "success", videos }),
      () => active && setState({ status: "error" }),
    );
    return () => {
      active = false;
    };
  }, []);

  if (state.status === "loading") {
    return <p aria-live="polite">Loading videos…</p>;
  }
  if (state.status === "error") {
    return <p role="alert">Unable to load videos.</p>;
  }
  if (state.videos.length === 0) {
    return <p>No videos are available yet.</p>;
  }

  return (
    <ul className="mt-6 grid gap-6" aria-label="Videos">
      {state.videos.map((video) => (
        <li key={video.id} className="rounded-xl border border-slate-200 p-4">
          <h2 className="font-semibold text-slate-950">{video.title}</h2>
          <p className="mt-1 text-sm text-slate-600">{video.byte_size.toLocaleString()} bytes</p>
          <video className="mt-4 w-full" controls preload="metadata" src={getVideoStreamUrl(video.id)}>
            Your browser does not support video playback.
          </video>
        </li>
      ))}
    </ul>
  );
}

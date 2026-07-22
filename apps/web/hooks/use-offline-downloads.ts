"use client";

import { useCallback, useEffect, useState } from "react";

import { getOfflineDownloadQueue, type DownloadQueueSnapshot } from "../lib/offline/download-queue";
import type { Video } from "../lib/api/videos";

export function useOfflineDownloads() {
  const [snapshot, setSnapshot] = useState<DownloadQueueSnapshot | null>(null);

  useEffect(() => {
    const queue = getOfflineDownloadQueue();
    let disposed = false;
    const update = () => {
      if (!disposed) setSnapshot(queue.getSnapshot());
    };
    const unsubscribe = queue.subscribe(update);
    update();
    void queue.initialize().then(update, update);

    return () => {
      disposed = true;
      unsubscribe();
    };
  }, []);

  const enqueueAndStart = useCallback(async (video: Video) => {
    const queue = getOfflineDownloadQueue();
    const enqueued = await queue.enqueue(video);
    if (enqueued) void queue.start().catch(() => undefined);
    return enqueued;
  }, []);

  const enqueueManyAndStart = useCallback(async (videos: Video[]) => {
    const queue = getOfflineDownloadQueue();
    const enqueued = await queue.enqueueMany(videos);
    if (enqueued > 0) void queue.start().catch(() => undefined);
    return enqueued;
  }, []);

  const retryAndStart = useCallback(async (videoId: string) => {
    const queue = getOfflineDownloadQueue();
    const retried = await queue.retry(videoId);
    if (retried) void queue.start().catch(() => undefined);
    return retried;
  }, []);

  return {
    snapshot,
    enqueueAndStart,
    enqueueManyAndStart,
    retryAndStart,
    continueDownloads: () => void getOfflineDownloadQueue().start().catch(() => undefined),
    abortActive: () => getOfflineDownloadQueue().abortActive(),
  };
}

# ADR-004: Offline library metadata and media storage foundation

## Status

Accepted for TASK-005 Blocks 1–2.

## Context

The PWA needs a durable local catalogue for future offline video playback. TASK-001 confirmed that Cache Storage can hold MP4 files and IndexedDB can preserve associated metadata on an iPhone, but the production application did not yet have an isolated local-storage boundary.

## Decision

- IndexedDB database `offline-reels` version 1 stores only local-video metadata in the `offlineVideos` object store.
- MP4 responses belong only in the separately versioned Cache Storage cache `offline-reels-media-v1`.
- Every media entry uses the validated, same-origin synthetic key `/offline-media/{uuid}`. Backend URLs, cursors, credentials and blobs are never stored in IndexedDB.
- A record becomes logically usable as `completed` only when its cache entry has the expected synthetic key, an allowed `video/mp4` content type and the expected byte size.
- IndexedDB and Cache Storage do not share a transaction. Startup reconciliation is the compensating mechanism: it marks stale downloads and invalid completed records as failed, and removes orphan media entries.
- The repository and cache adapter are browser-only at call time, not at module import time, so they remain safe to import from Next.js server-rendered code.
- Block 2 downloads one Backend stream at a time. Its `TransformStream` counts unchanged chunks and emits throttled progress while a single owned response body is transferred to `Cache.put()`. It deliberately does not use `ReadableStream.tee()`, response cloning, a Blob, an ArrayBuffer or a JavaScript chunk array for the downloader path.
- `putCachedVideoOwnedResponse()` makes the destructive ownership transfer explicit. The existing `putCachedVideo()` retains its clone-based API for callers that retain their response.
- The local queue persists lifecycle records in IndexedDB, but progress is memory-only: it writes `downloadedBytes = 0` when work starts and the exact final size only after Cache Storage validation succeeds. A failed or aborted attempt stores a safe error and zero downloaded bytes.
- Queue concurrency is one per browser tab. A user action starts or continues it; queued records survive reload, stale `downloading` records become `failed(download_interrupted)`, and it never auto-resumes after reload or a network recovery. Abort marks the active record `failed(download_aborted)` and pauses the queue. A quota failure also pauses it.

## Consequences

- Blocks 1–2 provide typed persistence, a sequential downloader and minimal `/videos` download controls without changing online playback or adding an offline playback route.
- Storage estimates use a 1.2 safety multiplier and a 50 MiB desired reserve. An unavailable estimate does not block a download; a known shortage fails the item and pauses the queue. Persistent-storage requests remain a future explicit user action.
- A single stream avoids the unbounded slower-branch buffering risk of `ReadableStream.tee()`, but Cache Storage implementation memory behavior—especially on iPhone—still needs device validation with large files.
- Service Worker, application-shell caching, `/offline`, cached-media Range handling and offline playback remain intentionally deferred to later TASK-005 blocks.
- Cache verification currently reads one targeted cached response to verify its byte size. Reconciliation never runs at import time and later UI integration must avoid blocking first render on validation of a large library.

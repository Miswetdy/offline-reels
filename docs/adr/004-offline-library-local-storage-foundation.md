# ADR-004: Offline library metadata and media storage foundation

## Status

Accepted for TASK-005 Block 1.

## Context

The PWA needs a durable local catalogue for future offline video playback. TASK-001 confirmed that Cache Storage can hold MP4 files and IndexedDB can preserve associated metadata on an iPhone, but the production application did not yet have an isolated local-storage boundary.

## Decision

- IndexedDB database `offline-reels` version 1 stores only local-video metadata in the `offlineVideos` object store.
- MP4 responses belong only in the separately versioned Cache Storage cache `offline-reels-media-v1`.
- Every media entry uses the validated, same-origin synthetic key `/offline-media/{uuid}`. Backend URLs, cursors, credentials and blobs are never stored in IndexedDB.
- A record becomes logically usable as `completed` only when its cache entry has the expected synthetic key, an allowed `video/mp4` content type and the expected byte size.
- IndexedDB and Cache Storage do not share a transaction. Startup reconciliation is the compensating mechanism: it marks stale downloads and invalid completed records as failed, and removes orphan media entries.
- The repository and cache adapter are browser-only at call time, not at module import time, so they remain safe to import from Next.js server-rendered code.

## Consequences

- Block 1 provides a typed persistence boundary and tests without changing `/videos` or adding a user-facing offline library.
- Service Worker, application-shell caching, `/offline`, download queue, downloader, progress UI and Range handling are intentionally deferred to later TASK-005 blocks.
- Cache verification currently reads one targeted cached response to verify its byte size. Reconciliation never runs at import time and later UI integration must avoid blocking first render on validation of a large library.

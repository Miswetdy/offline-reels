# Architecture

## Overview

Offline Reels is a personal application that allows users to prepare a personalized Instagram Reels feed in advance and watch it without an internet connection.

The system consists of several independent components:

1. Mobile App / PWA
2. Backend API
3. Feed Queue
4. Instagram Collector
5. Media Downloader
6. Video Storage

Each component has a clear responsibility and communicates only through defined interfaces.

---

# System Flow

The general data flow:

1. Instagram Collector accesses the user's personalized Instagram Reels feed through an authenticated server-side browser session.

2. Instagram Collector discovers new Reels and sends information about them to the Backend.

3. Backend creates and manages the user's feed queue.

4. Media Downloader downloads video files and validates downloaded media.

5. Video Storage stores prepared video files and related metadata.

6. Mobile App / PWA requests available videos from Backend and synchronizes them to local storage.

7. User watches videos from local storage without requiring an internet connection.

8. Watched status is synchronized back to Backend when the connection is available.

---

# Components

## Mobile App / PWA

Purpose:

Provide the user interface and offline viewing experience.

Responsibilities:

- Display the vertical Reels feed.
- Play locally stored videos.
- Manage offline mode.
- Store videos on the device.
- Track watched videos.
- Synchronize local state with Backend.
- Manage local storage limits.

Restrictions:

- The client must never store Instagram credentials.
- The client must communicate only with Backend API.
- The client must not directly interact with Instagram.

---

## Backend API

Purpose:

Serve as the main application layer between the client and internal services.

Responsibilities:

- Manage users.
- Manage feed state.
- Provide API endpoints for the mobile application.
- Track downloaded and watched videos.
- Manage synchronization between server and client.
- Coordinate background processes.

Restrictions:

- Backend should not contain Instagram-specific scraping logic.
- External integrations should be isolated in separate services.

---

## Feed Queue

Purpose:

Manage the order and availability of videos for each user.

Responsibilities:

- Store discovered Reels.
- Track video states.
- Prevent duplicate videos.
- Decide which videos should be synchronized to the device.
- Maintain the user's offline video buffer.

Possible video states:

- Discovered.
- Downloading.
- Ready on server.
- Downloaded to device.
- Watched.
- Deleted.

---

## Instagram Collector

Purpose:

Collect personalized Reels from Instagram.

Responsibilities:

- Maintain authenticated browser sessions.
- Open Instagram Reels.
- Discover new videos.
- Extract required metadata.
- Send discovered videos to Backend.

Restrictions:

- Instagram automation must be isolated from the rest of the system.
- Credentials and sessions must remain on the server.
- The collector should be replaceable without changing other components.

---

## Media Downloader

Purpose:

Download and prepare video files.

Responsibilities:

- Download video files.
- Validate downloaded files.
- Check file size and format.
- Handle download failures.
- Retry failed downloads.

Restrictions:

- Must support safe retries.
- Must avoid creating duplicate files.

---

## Video Storage

Purpose:

Store video files and metadata.

Responsibilities:

- Store downloaded videos.
- Store thumbnails if required.
- Provide access to Backend and synchronization services.
- Manage file lifecycle.

For the first video vertical slice, the Backend accesses MinIO through a replaceable storage adapter. The PWA receives video bytes only from `GET /videos/{id}/stream`; it never receives MinIO credentials or a direct object URL. The API streams a single HTTP byte range from storage in chunks.

For TASK-004, `GET /videos` is a Backend-owned cursor-paginated feed API. It signs opaque cursors with an application secret and uses the stable PostgreSQL order `created_at DESC, id DESC`; the PWA treats cursors as opaque and continues to communicate only with the Backend API. The `/videos` UI uses native browser scrolling and `IntersectionObserver` to select one active player. This changes neither the storage boundary nor the rule that the client must not contact MinIO directly.

---

# Security Principles

The system must follow these rules:

- Instagram credentials, cookies, and sessions must never be stored on the client.
- Secrets must never be committed to GitHub.
- Real user credentials must never be used in tests.
- External data must always be validated.
- Logs must not contain sensitive information.

---

# Offline Mode

Offline mode should work independently from Instagram availability.

When the user has no internet connection:

- The application uses locally stored videos.
- The user can browse the feed.
- The user can watch downloaded videos.
- The application stores local actions for future synchronization.

Internet is only required for:

- downloading new videos;
- synchronizing state;
- updating the feed queue.

---

# Local Offline Library

TASK-005 Blocks 1–2 introduce an isolated client-side persistence boundary without changing the online feed. The `offline-reels` IndexedDB database stores local-video metadata and lifecycle state; the separate `offline-reels-media-v1` Cache Storage cache stores MP4 responses. Entries use validated same-origin synthetic paths in the form `/offline-media/{uuid}` and never store Backend URLs, cursors, credentials or blobs in IndexedDB.

IndexedDB and Cache Storage do not have a common transaction. The Block 2 downloader fetches the existing Backend stream without a Range header, passes its one response body through a `TransformStream` that counts unchanged chunks and emits throttled progress, then transfers that body exactly once to Cache Storage. Cache validation precedes the IndexedDB `completed` transition. On any error it removes a possible cache entry and records a safe failed state; startup reconciliation compensates for stale downloads, missing or invalid cache entries, and orphan media entries.

The app-scoped queue is limited to one active download per browser tab. It persists queued/completed/failed states but keeps progress only in memory. It does not auto-resume on reload or network restoration; users explicitly continue queued work. Service Worker delivery, an offline route, cached-media Range responses and offline playback remain outside Blocks 1–2.

TASK-005 Block 3.1 extracts the shared `VerticalVideoFeed` UI boundary from the online `VideoList`. The reusable component owns only vertical scroll-snap playback: active-item selection with `IntersectionObserver` and rAF fallback, muted autoplay, pause behavior and the active-plus-next media window. `VideoList` remains the online data wrapper for Backend pagination, sentinel loading, deduplication and download controls. No offline route, Service Worker delivery or Cache Storage playback is implemented by this extraction.

TASK-005 Block 3.2 adds the browser-only `/offline` catalog. It runs reconciliation, reads only completed IndexedDB records and never requests a Backend catalog or starts the download queue. Its initial temporary Blob URL playback implementation has been replaced by the Service Worker media route described below; there is no Backend fallback.

TASK-005 Block 3.3 adds local-library management. A small coordinator deletes the Cache Storage entry before its IndexedDB record, or clears only the versioned media cache before `offlineVideos`. If metadata cleanup fails after cache cleanup, reconciliation prevents the stale record from being presented as completed. Neither operation affects Backend, MinIO, PostgreSQL or other cache namespaces.

TASK-005 Block 4.1 adds one production-only Service Worker using the Turbopack integration of Serwist. The worker is dynamically served at `/serwist/sw.js`, has scope `/`, and is registered automatically by `SerwistProvider`; the application does not register a second worker. Native `esbuild` is required to bundle `app/sw.ts` on Windows. The worker precaches static Next build assets and adds the literal `/offline`, `/videos`, and `/manifest.webmanifest` routes explicitly with a deterministic SHA-256 revision derived from the application-shell source inputs. This establishes the required fallback invariant: `/offline` is present in the precache before Serwist binds it as the navigation fallback for same-origin `GET /offline` requests, while the manifest does not require a network request from the installed shell. It does not define runtime caching, so Backend API requests, video streams, cross-origin resources and local Blob URLs are never cached by the Service Worker. Serwist's precache namespace is separate from `offline-reels-media-v1`; worker activation cleanup targets only outdated precache caches, while library delete/clear targets only the media cache.

TASK-005 Block 4.2 also precaches the revisioned `/videos` application shell, not its Backend catalog. Offline navigation to `/videos` can therefore boot React, whose uncached Backend request fails into a controlled offline state linking to `/offline`. The state uses both the browser network hint and an explicit fetch-level network-error classification, because `navigator.onLine` alone is not a reachability guarantee. `/offline` remains the only navigation fallback; unknown paths are not served with an incorrect offline-library document. The network indicator observes `navigator.onLine` and online/offline browser events without claiming local-media availability or triggering reloads. The worker uses `skipWaiting: false`: updates may wait until clients close, avoiding an application-controlled activation or multi-tab reload loop.

TASK-005 Block 5.1 adds an explicit Serwist route for same-origin `/offline-media/{uuid}`. The route accepts only exact validated synthetic paths without query parameters, opens only `offline-reels-media-v1`, and never calls `fetch`, writes to a cache, or inspects Serwist shell caches. `OfflineVideoList` passes these URLs directly to `VerticalVideoFeed`, retaining the active-plus-next source window without allocating MP4 Blob URLs. If no worker controls the page, playback is withheld behind a controlled readiness state rather than a Backend or Blob fallback.

TASK-005 Block 5.2 adds strict single-byte-range parsing to that route. `GET` without Range returns the full cached bytes as `200` with `Content-Length` and `Accept-Ranges: bytes`; `bytes=start-end`, `bytes=start-`, and `bytes=-suffixLength` return a correctly sliced `206` with inclusive `Content-Range`. Invalid, unsatisfiable and multipart ranges return `416` with `Content-Range: bytes */total`; multipart responses are intentionally not generated. HEAD returns the equivalent metadata without a body. The worker reads the complete cached response into a `Uint8Array`, then constructs a new response from the required slice. The cache entry remains unchanged and no slice is written back, but this has an O(file size) worker-memory cost that must be measured on iPhone before acceptance.

TASK-005 Block 6.1 hardens the Cache Storage/IndexedDB compensation boundary. Reconciliation considers a media response owned only after the corresponding `completed` record validates its synthetic key, MP4 content type and exact byte size. It changes interrupted, missing or invalid metadata to a safe failed state and removes zero-byte, orphan, and media retained by non-completed records. Cache Storage read/list failures do not result in a playable catalog; the page renders a controlled storage error instead. Downloader writes cache bytes first, validates them, and only then writes `completed` metadata. If a later metadata operation or local cleanup partially fails, a subsequent reconciliation removes or invalidates the inconsistent side without Backend access.

TASK-005 Block 6.2 keeps media lifecycle in `VerticalVideoFeed`. Only the active item and its next neighbor own a `src`; all other mounted players are paused and have their source removed with `load()` so the browser can release media resources. Page visibility and lifecycle transitions pause all players and invalidate pending asynchronous playback generations. `pageshow` intentionally does not start playback again. When a mutation removes the active item, the feed selects the next item in the prior order, or the previous item at the end of the list, while preserving stable video-id React keys. `/offline` does not render a player until a Service Worker controller exists; it separately reports an unsupported API and listens for `controllerchange` without reloading or falling back to Backend media or Blob URLs.

An online or offline media delivery failure is terminal for that card during its mounted feed session: the player pauses, removes `src`, calls `load()` to end native loading, and displays a safe per-video error. The failed item is excluded from later automatic source assignment, so active-item changes cannot create a request loop. Other cards remain scrollable and playable. This UI policy does not repair a server-side PostgreSQL/MinIO inconsistency and does not add a backend fallback.

---

# Development Principles

The architecture should prioritize:

- simple solutions;
- clear separation of responsibilities;
- replaceable external integrations;
- testability;
- maintainability.

New features should not bypass existing boundaries between components.

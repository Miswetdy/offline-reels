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

TASK-005 Block 3.1 extracts the shared `VerticalVideoFeed` UI boundary from the online `VideoList`. The reusable component owns only vertical scroll-snap playback: active-item selection with `IntersectionObserver` and rAF fallback, muted autoplay, pause behavior and a bounded media window. `VideoList` remains the online data wrapper for Backend pagination, sentinel loading, deduplication and download controls. No offline route, Service Worker delivery or Cache Storage playback is implemented by this extraction.

TASK-005 Block 3.2 adds the browser-only `/offline` catalog. It runs reconciliation, reads only completed IndexedDB records and never requests a Backend catalog or starts the download queue. Its initial temporary Blob URL playback implementation has been replaced by the Service Worker media route described below; there is no Backend fallback.

TASK-005 Block 3.3 adds local-library management. A small coordinator deletes the Cache Storage entry before its IndexedDB record, or clears only the versioned media cache before `offlineVideos`. If metadata cleanup fails after cache cleanup, reconciliation prevents the stale record from being presented as completed. Neither operation affects Backend, MinIO, PostgreSQL or other cache namespaces.

TASK-005 Block 4.1 adds one production-only Service Worker using the Turbopack integration of Serwist. The worker is dynamically served at `/serwist/sw.js`, has scope `/`, and is registered automatically by `SerwistProvider`; the application does not register a second worker. Native `esbuild` is required to bundle `app/sw.ts` on Windows. The worker precaches static Next build assets and adds the literal `/offline`, `/videos`, and `/manifest.webmanifest` routes explicitly with a deterministic SHA-256 revision derived from the application-shell source inputs. This establishes the required fallback invariant: `/offline` is present in the precache before Serwist binds it as the navigation fallback for same-origin `GET /offline` requests, while the manifest does not require a network request from the installed shell. It does not define runtime caching, so Backend API requests, video streams, cross-origin resources and local Blob URLs are never cached by the Service Worker. Serwist's precache namespace is separate from `offline-reels-media-v1`; worker activation cleanup targets only outdated precache caches, while library delete/clear targets only the media cache.

TASK-005 Block 4.2 also precaches the revisioned `/videos` application shell, not its Backend catalog. Offline navigation to `/videos` can therefore boot React, whose uncached Backend request fails into a controlled offline state linking to `/offline`. The state uses both the browser network hint and an explicit fetch-level network-error classification, because `navigator.onLine` alone is not a reachability guarantee. `/offline` remains the only navigation fallback; unknown paths are not served with an incorrect offline-library document. The network indicator observes `navigator.onLine` and online/offline browser events without claiming local-media availability or triggering reloads. The worker keeps `skipWaiting: false`; Serwist reports a waiting update to a compact safe-area-aware PWA notification. Only an explicit user click sends Serwist's supported `SKIP_WAITING` message to the waiting worker. The page reloads once after its `controllerchange`, never automatically during playback or download, and does not clear the separate media cache or IndexedDB.

TASK-005 Block 5.1 adds an explicit Serwist route for same-origin `/offline-media/{uuid}`. The route accepts only exact validated synthetic paths without query parameters, opens only `offline-reels-media-v1`, and never calls `fetch`, writes to a cache, or inspects Serwist shell caches. `OfflineVideoList` passes these URLs directly to `VerticalVideoFeed` without allocating MP4 Blob URLs. If no worker controls the page, playback is withheld behind a controlled readiness state rather than a Backend or Blob fallback.

TASK-005 Block 5.2 adds strict single-byte-range parsing to that route. `GET` without Range returns the full cached bytes as `200` with `Content-Length` and `Accept-Ranges: bytes`; `bytes=start-end`, `bytes=start-`, and `bytes=-suffixLength` return a correctly sliced `206` with inclusive `Content-Range`. Invalid, unsatisfiable and multipart ranges return `416` with `Content-Range: bytes */total`; multipart responses are intentionally not generated. HEAD returns the equivalent metadata without a body. The worker reads the complete cached response into a `Uint8Array`, then constructs a new response from the required slice. The cache entry remains unchanged and no slice is written back, but this has an O(file size) worker-memory cost that must be measured on iPhone before acceptance.

TASK-005 Block 6.1 hardens the Cache Storage/IndexedDB compensation boundary. Reconciliation considers a media response owned only after the corresponding `completed` record validates its synthetic key, MP4 content type and exact byte size. It changes interrupted, missing or invalid metadata to a safe failed state and removes zero-byte, orphan, and media retained by non-completed records. Cache Storage read/list failures do not result in a playable catalog; the page renders a controlled storage error instead. Downloader writes cache bytes first, validates them, and only then writes `completed` metadata. If a later metadata operation or local cleanup partially fails, a subsequent reconciliation removes or invalidates the inconsistent side without Backend access.

TASK-005 Block 6.2 keeps media lifecycle in `VerticalVideoFeed`. Distant mounted players are paused and have their source removed with `load()` so the browser can release media resources. Page visibility and lifecycle transitions pause all players and invalidate pending asynchronous playback generations. `pageshow` intentionally does not start playback again. When a mutation removes the active item, the feed selects the next item in the prior order, or the previous item at the end of the list, while preserving stable video-id React keys. `/offline` does not render a player until a Service Worker controller exists; it separately reports an unsupported API and listens for `controllerchange` without reloading or falling back to Backend media or Blob URLs.

An online or offline media delivery failure is terminal for that card during its mounted feed session: the player pauses, removes `src`, calls `load()` to end native loading, and displays a safe per-video error. The failed item is excluded from later automatic source assignment, so active-item changes cannot create a request loop. Other cards remain scrollable and playable. This UI policy does not repair a server-side PostgreSQL/MinIO inconsistency and does not add a backend fallback.

Post-iPhone hardening block 2 expands the shared source window to previous/current/next. The active item alone has `preload="auto"` and receives autoplay; its immediate previous and next neighbours retain their existing source with `preload="metadata"` and are paused. All other mounted players have no source. The source-assignment effect keeps an unchanged URL intact, so a backward swipe to the previous item does not require removing and reassigning its `src`. This preserves one component and lifecycle for both backend stream URLs and Service Worker offline URLs. Browser preload remains advisory; the offline single-range handler can still materialize a full cached MP4 in worker memory per media request, requiring post-change iPhone validation.

Post-iPhone hardening block 3 keeps that shared playback boundary and adds an explicit controls mode. `VideoList` uses the default native-controls/`object-contain` mode; `OfflineVideoList` selects Reels-like mode, which removes native controls, enables `loop`, uses `object-cover`, and starts with sound enabled. Its guarded startup first attempts normal audible playback; a `NotAllowedError` leaves that active item unmuted and paused with an explicit Play button, never a hidden muted-autoplay fallback. A tap-specific visibility state, separate from actual media pause state, reveals central SVG play/sound buttons only after an explicit tap-pause or that audible-policy rejection; only the current active video's guarded `play` event hides them. Its single pending timer transitions to either a temporary centre pause or temporary outer-10% edge 2× action, neither of which reveals controls. Movement, pointer cancellation and scroll restore a still-active temporary centre hold; active-item and page lifecycle cancellation never resume it. It never calls `preventDefault` or captures the pointer, leaving vertical scroll-snap to the browser. The feed distinguishes effective active from committed item: active selection controls pause/play and is reversible during a partial drag, so both cards retain their paused position and visible frame. A commit requires observer ratio ≥ 0.999 and both card/root edges within 2 CSS px; only then does the previous committed card gain a guarded offscreen reset at ratio 0. A fast return before commit resumes its saved position; a return after commit waits for any pending seek and starts at 0. Scoped Reels card styles suppress iOS callout, selection and video drag without affecting native `/videos`. Progress is derived from active-video media events rather than a persistent animation frame. Reels lays metadata above progress and the shared safe-area-aware bottom navigation. Its scoped `backdrop-filter` and translucent fallback blur only the lower navigation zone, not the video element. The two real navigation links point to `/videos` (temporarily **Главная и загрузка**) and `/offline` (**Офлайн-библиотека**), exposing the current route through `aria-current`. The active startup path starts guarded playback as soon as `HAVE_METADATA` is available or `loadedmetadata` arrives; an actual reset seek still waits for current `seeked`, and `canplay` never creates a second start. Future author/caption fields remain outside this UI boundary until TASK-006. This UI mode does not change Service Worker delivery, Cache Storage, IndexedDB, queue, or Backend contracts.

The full-screen commit is atomic: it marks the prior committed card reset-required and immediately checks cached intersection and card/root geometry. This makes `A=zero` before `B=full` equivalent to `B=full` before `A=zero`; neither order waits for another observer callback. Per-card preparation progresses through reset-required, reset-in-flight and prepared-at-zero. An offscreen card becomes visible only after its seek and a decodable first frame. A matching prepared card returns without another seek or visibility transition; a return during preparation waits for the existing guarded operation.

The final lower-layout tuning is shared by both routes through CSS variables: navigation uses the safe area plus a bounded adaptive lift, while native `/videos` reserves that same footprint. Reels puts its non-seekable progress in a pointer-inert transparent layer between metadata and navigation, over one fixed shared glass backdrop that continues through the pill and safe area. That backdrop alone owns the scoped blur/saturation and opaque fallback; it never applies a filter to the video element and does not participate in playback, scroll or gesture state.

## iPhone PWA acceptance findings

The browser-facing Backend URL is a required build-time public value,
`NEXT_PUBLIC_API_BASE_URL`; Funnel staging uses one HTTPS origin with `/api` as
its API path prefix. `/offline-media/{id}` remains same-origin, so the Service
Worker media route and media cache do not contact the Backend after download.

The completed iPhone run showed that Safari and the installed Home Screen PWA
use separate offline-storage contexts. Users must install the PWA before
downloading videos into the library. It also exposed media compatibility as an
ingestion boundary: a VP9 MP4 did not play, whereas H.264 with `yuv420p` and
`faststart` did. Normalization therefore belongs before future storage and
playback work. Post-iPhone hardening block 2 now retains the previous/current/
next source window to improve backward navigation while bounding sources to
three. Block 3 now gives only `/offline` Reels-like controls while `/videos`
keeps native controls; installed-PWA behavior remains subject to block 4
real-device acceptance.

## Media normalization foundation

Stage 1A adds an isolated server-side `app.media` boundary. `probe_media` invokes
`ffprobe` without a shell and returns typed stream metadata; every source and
normalized output must also pass a full `ffmpeg -map 0 -f null -` decode
validation. The MVP canonical output is MP4 with H.264 video, `yuv420p`, AAC
audio when audio exists, and `faststart` metadata.

Compatibility chooses the least destructive path: valid H.264/`yuv420p` media
with AAC-or-no-audio is remuxed with copied streams and `+faststart`. VP9, AV1,
Opus, unsupported pixel formats, and other incompatible inputs are transcoded
with `libx264` Main level 4.1, CRF 23, `yuv420p`, and optional AAC 128k audio.
`normalize_video(source)` creates a private temporary directory and yields the
verified result only inside a controlled context; Stage 1B must upload
`result.output_path` before leaving that context. The output is removed on both
normal and exceptional exit, rather than being left to garbage collection.
Internally, normalization writes to a sibling temporary file, then reprobes and
decodes it before atomically publishing into that private directory.

Stage 1B consumes this context from the existing synchronous seed service. It
uses only the normalized MP4 bytes and the generated `videos/{sha256}.mp4`
key; user filenames and original bytes never reach MinIO. The sequence is
normalization → MinIO upload (`video/mp4`) → PostgreSQL upsert/commit. If
normalization or upload fails, no row is created. If the database write fails
after a newly created object, the session rolls back and the service makes a
best-effort MinIO delete, logging a compensation failure separately. This is a
compensating workflow rather than a distributed transaction. New rows store
nullable strategy, source/output codecs, dimensions, duration, normalized byte
size, audio presence and timestamp; existing objects are neither migrated nor
changed, and the public catalog contract is unchanged.

---

# Development Principles

The architecture should prioritize:

- simple solutions;
- clear separation of responsibilities;
- replaceable external integrations;
- testability;
- maintainability.

New features should not bypass existing boundaries between components.

## Production-like VPS foundation

The local [`compose.yaml`](../compose.yaml) remains a desktop-development stack and deliberately publishes convenience ports. Production-like deployment is isolated in [`deploy/docker-compose.prod.yml`](../deploy/docker-compose.prod.yml): Caddy is the only public service and terminates HTTPS for separate application and API domains. The web service keeps the existing Next.js standalone runtime (`node server.js`), while FastAPI runs Uvicorn only; a one-shot `migrate` service runs Alembic deliberately before API rollout. Both production commands use `uv run --no-sync`, so they cannot install missing development dependencies at runtime.

PostgreSQL, Redis and MinIO live only on an `internal: true` Docker network. MinIO root credentials are limited to MinIO and the idempotent bootstrap job; the API receives a separate bucket-scoped application user. Caddy preserves the API's HTTP Range response headers and does not cache video streams. See [`deploy/README.md`](../deploy/README.md) for the operator sequence.

## Public Funnel staging

For real-iPhone staging without a VPS, `deploy/docker-compose.funnel-smoke.yml`
overlays the production Compose topology. It publishes Caddy only on Windows
loopback and mounts `Caddyfile.funnel`; Tailscale Funnel terminates public TLS
on one `https://<machine>.<tailnet>.ts.net` origin and proxies to that loopback
port. Caddy strips only the `/api` prefix before forwarding to FastAPI and
routes every other request to the Next.js standalone server. The browser API
base URL can therefore be either a normal origin or an origin with a path
prefix; endpoint construction preserves the configured prefix. The Service
Worker's offline media route remains same-origin and does not contact the API.

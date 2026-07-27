# Status

## Current stage

Media normalization ingestion integration (Stage 1B).

## Completed

- Defined product idea.
- Defined MVP scope.
- Created initial architecture.
- Created project documentation.
- Connected GitHub repository.
- Defined Codex workflow.
- Completed TASK-001: iOS offline video storage spike.
- Completed TASK-002: production bootstrap with Next.js web app, FastAPI API, PostgreSQL, Redis, MinIO, Docker Compose, health checks and an empty reversible Alembic migration.
- Implemented TASK-003: videos table, MinIO adapter, idempotent MP4 seed, video list and Backend API streaming with single HTTP Range support.
- Implemented TASK-004: HMAC-signed keyset pagination for `GET /videos`, deterministic batch MP4 seed, and a native scroll-snap multi-video feed with muted autoplay, shared sound state and incremental loading.
- Completed the current iPhone PWA acceptance run through Tailscale Funnel staging.

## Current focus

Stage 1B connects the typed Stage 1A media boundary to the existing synchronous
`seed_video` ingest. Every newly seeded input is probed and decode-validated,
then remuxed or transcoded to the canonical MP4 before MinIO upload and the
PostgreSQL insert. The verified temporary output lives only inside the
normalization context during upload and is removed on every exit path. A
successful seed records nullable normalization metadata; existing objects and
catalog DTOs remain unchanged.

## Production-like VPS foundation

Implemented the first deployment foundation without changing local development:

- added an isolated production Compose file with Caddy as the only public service;
- kept Next.js standalone runtime (`node server.js`);
- separated Alembic migration into a one-shot `migrate` service;
- added private PostgreSQL, authenticated persistent Redis, and private MinIO volumes;
- added an idempotent MinIO bucket/application-user bootstrap job;
- added a safe production environment template and VPS launch/verification guide.
- hardened production API and migration commands with `uv run --no-sync` after local smoke showed that plain `uv run` attempted an unavailable development-dependency sync at runtime.
- verified the production Compose foundation locally through Docker Desktop: health endpoints, Caddy routes, CORS, MinIO bootstrap, migration idempotency, Range delivery, Redis AOF, and persistence across a restart.

## Public Tailscale Funnel staging

Verified a separate staging override for iPhone PWA testing: Funnel provides
one public HTTPS `*.ts.net` origin to a loopback-only local Caddy instance,
which routes `/api/*` to FastAPI after removing the prefix and all other paths
to Next.js. The browser API URL builder now explicitly supports an optional
path prefix, so the same code supports both the existing two-origin deployment
and the Funnel single-origin layout. It is intentionally not a persistent
production environment.

Not implemented in this block: backup/restore scripts, automated deployment,
monitoring, or a concrete VPS configuration.

## Next step

Run the local production-like normalization smoke, then implement
previous/current/next preload and Reels-like controls before repeating the
installed-PWA iPhone acceptance with normalized input.

## Recent decisions

Added:
- Technical decisions documentation.
- Technical risks documentation.
- Изолированный React/Vite PWA spike в `spikes/ios-offline-storage`.
- Cache Storage для тестового MP4 и IndexedDB только для успешно сохранённых метаданных.
- Автоматические тесты ключевой логики spike и инструкция по ручной проверке на iPhone.
- На iPhone подтверждено удаление тестового видео: оно не возвращается после перезапуска PWA.
- В интерфейсе разделены точный размер готовых видео и приблизительное origin-wide использование browser storage.
- TASK-001 пройден на iPhone 16 Pro с iOS 26.5.2 и 44,2 ГБ свободного места: видео размером 13 864 238 байт сохранилось после перезапуска PWA и воспроизвелось в авиарежиме.
- Для MVP принят подход: Cache Storage для видео и IndexedDB для метаданных готовых видео.
- Reproducible Docker Compose bootstrap added: Node.js 24.14.0/Next.js web app and Python 3.14.3/FastAPI API with PostgreSQL, Redis and MinIO.
- API exposes `/health/live` (FastAPI process only), `/health/ready` (PostgreSQL and Redis only), and independent `/health/minio` diagnostics.
- Alembic has an empty, reversible initial migration; Instagram collection, downloads, authentication, feed logic, Celery and production offline caching remain unimplemented.
- Web dependency security triage updated Vitest to 4.1.10 and removed its critical development-only advisory. The current dependency tree uses Next.js 16.2.11 and retains three high npm-audit findings: optional `sharp` 0.34.5 plus two advisories through Next.js's nested PostCSS 8.4.31. No unsafe force fix, override or Next.js downgrade was applied.
- TASK-003 streams video through Backend API rather than presigned storage URLs. Integration tests use isolated PostgreSQL and MinIO infrastructure.
- TASK-003 was validated end-to-end: idempotent seed uploaded the 13,864,238-byte spike MP4, `/videos` returned one record, HTTP streaming returned `200` and `206`, multipart Range returned `416`, and the video remained available after `make down`/`make up`.
- TASK-004 uses `created_at DESC, id DESC` keyset pagination with an HMAC-SHA-256 signed opaque cursor. The cursor secret is required at runtime and never belongs in Git.
- TASK-004 keeps loaded video elements mounted while validating native scroll-snap UX. To avoid Chromium open-ended Range downloads from every mounted element, only the active player and its next neighbor receive stream URLs; all remaining cards stay mounted without a source. Full DOM virtualization remains a future real-device performance task.
- The active-player selection retains the latest `IntersectionObserver` ratio for every feed card, resolves ties by the feed center, and has a requestAnimationFrame-throttled scroll fallback for browsers that emit only partial observer callback batches.
- Real Instagram Reels passed the manual TASK-004 feed smoke scenario in Chrome and Yandex Browser. The earlier issue was limited to some third-party test MP4 encodings, not pagination, active-player selection, the media window, Range streaming or the Backend API. A future ingestion task must define media validation and, if needed, normalization or transcoding for a safe MVP format; no transcoding was added to TASK-004.
- TASK-005 Block 1 adds the versioned `offline-reels` IndexedDB schema and `offline-reels-media-v1` media cache behind typed browser-only adapters. Reconciliation marks stale or invalid local records failed and removes orphan cache entries; Block 2 builds on this foundation.
- TASK-005 Block 2 adds a one-at-a-time, explicitly user-started local download queue. It passes one Backend stream through `TransformStream` directly to an owned Cache Storage response, avoiding `ReadableStream.tee()` and downloader response cloning. Progress is in-memory only; IndexedDB receives `0` at start and the verified final byte count only on completion. Downloads do not auto-resume after reload or network restoration; abort and quota failures pause the queue. Service Worker, `/offline`, cached-media Range delivery and offline playback are still not implemented.
- TASK-005 Block 3.1 separates reusable vertical playback UI from the online data layer. `VerticalVideoFeed` receives typed items and media URLs, exposes optional actions and active-item callbacks, and retains the observer/rAF selection and two-source media window. `VideoList` still owns online requests, cursor pagination and local-download controls; `/offline` is not implemented.
- TASK-005 Block 3.2 adds `/offline` as a local-only completed-video catalog with an exact library-size summary and approximate origin usage/quota. The temporary Cache Storage-to-Blob URL adapter is constrained to the active-plus-next playback window and always revokes its URLs. It is not a Service Worker replacement: offline reload and cached HTTP Range responses remain unimplemented.
- The Block 2 downloader uses `fetch(..., { cache: "no-store" })`. The API CORS policy therefore explicitly permits `Cache-Control` in addition to `Range`, as well as `GET` and `HEAD`, for the configured `FRONTEND_ORIGIN`; it exposes the media response headers needed by the downloader. This keeps the origin allowlist explicit and does not enable credentials or wildcards.
- TASK-005 Block 4.1 adds a Turbopack-compatible Serwist application shell. `@serwist/turbopack`, `serwist` and native `esbuild` build exactly one dynamically served worker at `/serwist/sw.js`; `SerwistProvider` registers it at scope `/` only in production. The Turbopack glob manifest contains only static assets, not literal App Router routes, so the worker adds `/offline`, `/videos`, and `/manifest.webmanifest` explicitly with deterministic SHA-256 revisions derived from application-shell build inputs. The offline navigation fallback is intentionally restricted to `/offline`; API, streams and media are not runtime-cached. Serwist shell-cache cleanup only targets its precache names and leaves `offline-reels-media-v1` untouched.
- TASK-005 Block 4.2 adds an explicit revisioned `/videos` application shell so the page can render a controlled offline state without reusing old API data. `/videos` is not a navigation fallback and unknown routes are not answered with `/offline`. `navigator.onLine` plus browser events drive an informational, SSR-safe UI indicator only; catalog fetch failures are separately classified so a disconnected request renders the offline state even if a browser keeps `navigator.onLine` true. The worker has no runtime caching, does not force `skipWaiting`, and has no application-triggered update/reload action; a waiting worker applies after existing clients close.
- TASK-005 Block 5.1 registers a same-origin `GET /offline-media/{uuid}` route in the existing Serwist worker. It validates the exact synthetic path, reads only `offline-reels-media-v1`, preserves cached MP4 headers, and returns controlled `404`/`400`/`503` responses without network fallback. `/offline` uses the synthetic URLs directly, while a page not yet controlled by the worker shows a controlled readiness message rather than silently recreating Blob URLs. Range requests are rejected as unsupported; correct `206`/`416` byte-range behavior is deferred.
- TASK-005 Block 5.2 replaces the temporary Range rejection. The worker supports `bytes=start-end`, `bytes=start-`, and `bytes=-suffixLength`; it clamps a valid end to the cached file size and preserves safe media validators. It returns `Accept-Ranges: bytes`, correct `Content-Length` and `Content-Range` for `206`, and `Content-Range: bytes */total` for `416`. Multiple ranges are deliberately unsupported and return `416`; no multipart response is generated. HEAD returns equivalent metadata without a body.
- TASK-005 Block 6.1 makes local reconciliation idempotent across interrupted downloads and partial cleanup. Only a metadata record whose cached MP4 validates remains `completed`; cache entries belonging to failed records, missing metadata, zero-byte bodies or invalid media are deleted. Cache Storage failures become controlled local-storage errors, while delete/clear retain their cache-first, reconciliation-backed compensation order. Quota, unavailable browser storage and interrupted download states remain typed safe errors; iPhone quota and long-session acceptance are still pending.
- TASK-005 Block 6.2 pauses local playback on visibility/page lifecycle transitions and prevents stale asynchronous `play()` work from reviving an old item. Source assignment stays bounded to active plus next items during rapid navigation and list mutations; active-item removal selects a valid successor without a backend request. Worker readiness is controlled through `navigator.serviceWorker.controller` and `controllerchange`, with no automatic reload. The Range handler still reads a cached MP4 once into worker memory per request; real iPhone memory and lifecycle acceptance remain pending.
- A manual smoke exposed the accepted PostgreSQL/MinIO inconsistency where metadata can outlive a deleted MinIO object. `VerticalVideoFeed` now treats a media `error` as terminal for that card: it clears the source and native loading state, shows a safe local message, and suppresses automatic source retries. Neighboring cards remain usable; no automatic PostgreSQL/MinIO reconciliation or backend fallback was added.

## Current open questions

- Exact synchronization strategy.
- Instagram session management.
- Media delivery architecture.
- Долгосрочная сохранность Cache Storage/IndexedDB и поведение при ограничении квоты iOS.

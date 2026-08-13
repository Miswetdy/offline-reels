# Status

## Stage 8 local reserve management

The PWA now has a foreground reserve controller that reconciles local media,
uses durable device-only reserve settings, requests bounded collection only when
the full ready catalog is short, and fills only missing Reels sequentially.
Migration `0008` stores redacted account-owned device reports; IndexedDB plus
Cache Storage remains the local truth. Closed-iOS background execution is not
claimed. The disposable Chromium iPhone-viewport E2E now passes: bounded
collection, reload deduplication, offline `/offline`, quota pause/resume,
cancel preservation, safe UI redaction and no-store management/reserve checks.
Its random Compose project, volumes, images and artifacts were removed after
acceptance. Manual iPhone acceptance is also complete through a temporary
Tailscale Funnel and a fully isolated synthetic fixture: Safari and the
Home-Screen installation correctly kept separate device-local libraries,
each filled from the same ready catalog without an extra collection run.
The check covered pairing, synthetic login, target fill, offline `/offline`,
reload/Home-Screen no-op, network return, pause/resume, quota simulation, UI
redaction, and server-side cancellation. During acceptance, cancel was
hardened to cancel the cycle-owned server run, management fetches gained a
15-second deadline, and the fixture received an explicitly build-time-only
quota control. Funnel and all fixture containers, volumes, networks, images,
and test artifacts were removed afterwards.

## Current stage

Stage 7 connects the canonical PWA dashboard to the protected Stage 6
management API while preserving the existing offline library, sequential queue
and `/offline` player. Device pairing remains operator-assisted: the dashboard
accepts a one-time code but never stores or displays it. The management cookie
is HttpOnly; an in-memory CSRF capability is refreshed from the protected
same-origin session endpoint after a PWA restart and is cleared on revoke/401.
Instagram login accepts only the fixed HTTPS same-origin Stage 4 `/connect/…`
route, collection/normalization/local-download progress uses confirmed counters
only, and IDs, media details and raw backend errors stay hidden. Management and
login capability responses are never cached; `/` and `/offline` retain their
offline shell behavior. Auto-collection is deliberately unavailable because
`scheduler_active=false`. The combined disposable Stage 7 mobile-viewport E2E
fixture has passed against synthetic PostgreSQL/MinIO, fixture gateway,
Collector and normalizer services; its exact Compose resources were removed
after acceptance. A real iPhone Stage 7 acceptance remains pending and needs
separate explicit approval; Stage 4 Risk 17 remains open. No live Instagram,
Funnel or PWA was launched during implementation.

Stage 4 secure mobile login is implemented in the working tree: one-time
hashed links, an isolated same-origin gateway, a non-root Chromium image and a
dedicated persistent account profile for the duration of an active login
deployment. Windows Docker Desktop manual iPhone Safari acceptance confirmed
the real remote Instagram login/challenge, profile confirmation and the local
success-screen UX; the authenticated Instagram feed was not exposed after
completion. The business API did not request or persist credentials, while the
remote-browser keyboard/pointer transport remained a deliberate trust
boundary. Post-acceptance cleanup removed the sensitive test browser profile,
the temporary Stage 4 database, Funnel state and the local staging secrets.
The current Windows-compatible runtime keeps `login-browser` non-root with
`cap_drop: ALL`, but uses `seccomp=unconfined` for that container only. It is
therefore functionally complete, not production-hardened. The Ubuntu VirtualBox
synthetic Chromium sandbox acceptance did not complete and is not evidence of
Linux deployment readiness; Risk 17 remains open. The staging UI has an
operator-created one-time link and **Open browser** control; a future protected
management/dashboard flow will create that session and enter the login flow
without exposing credentials to the business API. Collector remains untouched;
Stage 5 now adds a separate browser-free normalizer worker. The preserved
ten-Reel Collector smoke was manually accepted after migration `0006`: all ten
sources became ready catalog videos, completed on attempt one and were cleaned
post-commit; no staging, pending, running or failed jobs remain. Stage 3C.2
remains separate.

Post-iPhone hardening block 4A is implemented: `/` is the canonical offline-library dashboard, `/offline` is the clean Reels surface, and `/videos` is a legacy redirect. Instagram Collector Stage 3B is a manually invoked, bounded three-Reel operator composition over Stage 3A adapters. A test-account live run successfully confirmed three session-first downloads, validations, MinIO publications, PostgreSQL commits, two targeted transitions, durable `source_ready` Reels and read-only verification without changing `videos`. Stage 3C.1 then continued that same account-owned reserve from three to ten: seven new sources committed, six transitions confirmed, `videos` remained empty and the final read-only verifier passed. Stage 3C.2 now adds a separate non-root Linux Collector image and a disposable internal-network fixture cycle over real PostgreSQL/MinIO; automated and PowerShell manual synthetic acceptance both passed, and the API image remains browser-free. Live Instagram in the container has not been tested.

The disposable synthetic mobile fixture and the synthetic iPhone Stage 7 PWA
acceptance passed. Stage 4 real remote login also passed independently. The
combined retained Stage 4 profile → Collector → normalizer → PWA chain is not
accepted on Windows Docker Desktop: isolated non-root Chromium preflight,
including direct private CDP, closed before browser readiness because of a
Docker Desktop sandbox incompatibility. It must be re-accepted on Linux staging
or a real server. No `--no-sandbox`, root browser, privileged container or
`SYS_ADMIN` workaround was applied. Risk 17 remains open.

## Completed

- Defined product idea.
- Defined MVP scope.
- Created initial architecture.
- Created project documentation.

## Instagram Collector roadmap

1. Architecture foundation.
2. Fixture-driven Collector engine.
3. Production Collector runtime: 3A adapters, 3B bounded three-Reel operator
   run, then 3C Linux/container ten-Reel verification.
4. Phone-based Instagram connection.
5. Normalization queue.
6. Collector backend API.
7. Dashboard integration.
8. Local reserve management.
9. Viewing, delayed deletion and replenishment.
10. Reliability and security.
11. Final acceptance.
- Connected GitHub repository.
- Defined Codex workflow.
- Completed TASK-001: iOS offline video storage spike.
- Completed TASK-002: production bootstrap with Next.js web app, FastAPI API, PostgreSQL, Redis, MinIO, Docker Compose, health checks and an empty reversible Alembic migration.
- Implemented TASK-003: videos table, MinIO adapter, idempotent MP4 seed, video list and Backend API streaming with single HTTP Range support.
- Implemented TASK-004: HMAC-signed keyset pagination for `GET /videos`, deterministic batch MP4 seed, and a native scroll-snap multi-video feed with muted autoplay, shared sound state and incremental loading.
- Completed the current iPhone PWA acceptance run through Tailscale Funnel staging.

## Current focus

Instagram Collector Stage 3B retains the network-free fixture service over the
stage 1 account, collection-run, Reel pipeline and normalization-job state. It
proves `pause -> temporary download -> validation -> publication -> one DB
transaction -> advance`, including compensation of an object created by the
failed attempt. Fixture storage and SQLite are isolated from production settings.
The explicit headed operator composition now wires the optional isolated
Playwright feed, minimal in-memory session CookieJar, session-first yt-dlp,
ffprobe and MinIO source storage. Its bounded test-account run successfully
validated three durable source commits and two targeted transitions; the
post-run verifier also confirmed the exact MinIO/object and `videos` deltas. A
durable commit gates each transition: positions 1 and 2 have one
bounded retry wheel after an unconfirmed transition, while position 3 never
scrolls. Scheduler, Collector API and frontend remain absent. Stage 5 provides
a separate normalizer worker with PostgreSQL leases, MinIO staging/final
publication, safe retry/reconciliation and post-commit source cleanup; it does
not start from FastAPI. Stage 4 now supplies a separate mobile login browser boundary but does
not invoke a Collector run. Windows/iPhone functional acceptance succeeded, but
the Windows `login-browser` seccomp exception means hardened Linux deployment
proof remains open under Risk 17. The preserved Stage 3C PostgreSQL/MinIO smoke
state remains separate, and the validated local spike is not copied into
production.

Block 4A keeps `/offline` as the Reels-like control mode through the shared
`VerticalVideoFeed`; `/videos` is now a legacy redirect and no longer carries an
online feed or native player. `/` is a video-free dashboard that loads the full
paginated server catalog into the existing sequential offline queue. Offline video loops with `object-cover` and starts with sound enabled. It first attempts normal audible autoplay; an iOS policy
rejection leaves the video unmuted and paused with an explicit Play control,
never a silent muted fallback. Explicit tap-pause state alone otherwise reveals
central SVG controls, which hide on the current video's confirmed guarded
`play` event. Holds remain temporary and never reveal those controls. Active
selection is reversible and only pauses/plays cards: partial A↔B reversals keep
both saved positions and frames. A separate full-screen commit (ratio ≥ 0.999
and 2 CSS px geometry tolerance) permits only the previous committed card to
seek to 0 offscreen; a post-commit return starts at 0 with guarded seek fallback.
Reels-only styles suppress iOS callout, selection and drag while the gesture
state machine preserves native vertical scrolling.

The full-screen commit atomically marks the prior committed card and immediately
checks cached intersection and root geometry. Consequently, either observer
order (`A=0` before `B=full`, or the reverse) produces one offscreen reset.
The card progresses through reset-required, reset-in-flight and
prepared-at-zero; it is shown after a decodable first frame and returns without
a second seek or hidden-frame transition.

The final visual tuning uses a bounded safe-area-aware navigation lift. Reels
places progress in a transparent non-interactive layer over one fixed shared
glass backdrop that continues through the pill and safe area. The shared navigation marks `/` (**Главная**) or `/offline` (**Рилсы**) active. This is CSS/DOM layout work only and does not alter media, gesture or scroll lifecycles.

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

Next, repeat the unaccepted real Stage 4 profile → Collector → normalizer → PWA
chain on Linux staging or a real server. The synthetic fixture/iPhone Stage 7
acceptance and the separate Stage 4 remote-login acceptance are complete. No
arbitrary `return_url`, credential form or dashboard-to-Instagram direct link
is planned.

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
- TASK-004 keeps loaded video elements mounted while validating native scroll-snap UX. Post-iPhone hardening block 2 extends the source window to previous/current/next: active uses `preload="auto"`, neighbours use `preload="metadata"`, and all distant cards remain mounted without a source. Full DOM virtualization remains a future real-device performance task.
- The active-player selection retains the latest `IntersectionObserver` ratio for every feed card, resolves ties by the feed center, and has a requestAnimationFrame-throttled scroll fallback for browsers that emit only partial observer callback batches.
- Real Instagram Reels passed the manual TASK-004 feed smoke scenario in Chrome and Yandex Browser. The earlier issue was limited to some third-party test MP4 encodings, not pagination, active-player selection, the media window, Range streaming or the Backend API. A future ingestion task must define media validation and, if needed, normalization or transcoding for a safe MVP format; no transcoding was added to TASK-004.
- TASK-005 Block 1 adds the versioned `offline-reels` IndexedDB schema and `offline-reels-media-v1` media cache behind typed browser-only adapters. Reconciliation marks stale or invalid local records failed and removes orphan cache entries; Block 2 builds on this foundation.
- TASK-005 Block 2 adds a one-at-a-time, explicitly user-started local download queue. It passes one Backend stream through `TransformStream` directly to an owned Cache Storage response, avoiding `ReadableStream.tee()` and downloader response cloning. Progress is in-memory only; IndexedDB receives `0` at start and the verified final byte count only on completion. Downloads do not auto-resume after reload or network restoration; abort and quota failures pause the queue. Service Worker, `/offline`, cached-media Range delivery and offline playback are still not implemented.
- TASK-005 Block 3.1 separates reusable vertical playback UI from the online data layer. `VerticalVideoFeed` receives typed items and media URLs, exposes optional actions and active-item callbacks, and retains the observer/rAF selection and source window. `VideoList` still owns online requests, cursor pagination and local-download controls; `/offline` is not implemented.
- TASK-005 Block 3.2 adds `/offline` as a local-only completed-video catalog with an exact library-size summary and approximate origin usage/quota. Its initial temporary Cache Storage-to-Blob adapter was later replaced by the Service Worker media route; production playback no longer creates Blob URLs from the media cache.
- The Block 2 downloader uses `fetch(..., { cache: "no-store" })`. The API CORS policy therefore explicitly permits `Cache-Control` in addition to `Range`, as well as `GET` and `HEAD`, for the configured `FRONTEND_ORIGIN`; it exposes the media response headers needed by the downloader. This keeps the origin allowlist explicit and does not enable credentials or wildcards.
- TASK-005 Block 4.1 adds a Turbopack-compatible Serwist application shell. `@serwist/turbopack`, `serwist` and native `esbuild` build exactly one dynamically served worker at `/serwist/sw.js`; `SerwistProvider` registers it at scope `/` only in production. The Turbopack glob manifest contains only static assets, not literal App Router routes, so the worker adds `/offline`, `/videos`, and `/manifest.webmanifest` explicitly with deterministic SHA-256 revisions derived from application-shell build inputs. The offline navigation fallback is intentionally restricted to `/offline`; API, streams and media are not runtime-cached. Serwist shell-cache cleanup only targets its precache names and leaves `offline-reels-media-v1` untouched.
- TASK-005 Block 4.2 adds an explicit revisioned `/videos` application shell so the page can render a controlled offline state without reusing old API data. `/videos` is not a navigation fallback and unknown routes are not answered with `/offline`. `navigator.onLine` plus browser events drive an informational, SSR-safe UI indicator only; catalog fetch failures are separately classified so a disconnected request renders the offline state even if a browser keeps `navigator.onLine` true. The worker has no runtime caching and does not force `skipWaiting`.
- TASK-005 Block 5.1 registers a same-origin `GET /offline-media/{uuid}` route in the existing Serwist worker. It validates the exact synthetic path, reads only `offline-reels-media-v1`, preserves cached MP4 headers, and returns controlled `404`/`400`/`503` responses without network fallback. `/offline` uses the synthetic URLs directly, while a page not yet controlled by the worker shows a controlled readiness message rather than silently recreating Blob URLs. Block 5.2 subsequently added the current single-range `206`/`416` behavior.
- TASK-005 Block 5.2 replaces the temporary Range rejection. The worker supports `bytes=start-end`, `bytes=start-`, and `bytes=-suffixLength`; it clamps a valid end to the cached file size and preserves safe media validators. It returns `Accept-Ranges: bytes`, correct `Content-Length` and `Content-Range` for `206`, and `Content-Range: bytes */total` for `416`. Multiple ranges are deliberately unsupported and return `416`; no multipart response is generated. HEAD returns equivalent metadata without a body.
- TASK-005 Block 6.1 makes local reconciliation idempotent across interrupted downloads and partial cleanup. Only a metadata record whose cached MP4 validates remains `completed`; cache entries belonging to failed records, missing metadata, zero-byte bodies or invalid media are deleted. Cache Storage failures become controlled local-storage errors, while delete/clear retain their cache-first, reconciliation-backed compensation order. Quota, unavailable browser storage and interrupted download states remain typed safe errors; iPhone quota and long-session acceptance are still pending.
- TASK-005 Block 6.2 pauses local playback on visibility/page lifecycle transitions and prevents stale asynchronous `play()` work from reviving an old item. Source assignment stays bounded during rapid navigation and list mutations; active-item removal selects a valid successor without a backend request. Worker readiness is controlled through `navigator.serviceWorker.controller` and `controllerchange`, with no automatic reload. The Range handler still reads a cached MP4 once into worker memory per request; real iPhone memory and lifecycle acceptance remain pending.
- Post-iPhone hardening block 2 changes the shared media window to previous/current/next. The active player keeps `preload="auto"` and autoplay; both adjacent players retain a source with `preload="metadata"` and remain paused. Distant and terminally failed players clear `src` and call `load()`. This improves backward navigation without changing API pagination, downloader/queue, IndexedDB, Cache Storage or Service Worker contracts. A real iPhone smoke is required because `preload` is advisory and offline Range handling can materialize an MP4 in worker memory.
- Post-iPhone hardening block 3 adds an explicit Reels-like mode to the shared `VerticalVideoFeed` and enables it only for `/offline`; block 4A later makes `/videos` a legacy redirect. Reels initializes unmuted and first attempts guarded audible playback. If iOS rejects that autoplay, it stays unmuted and paused with an accessible Play control; no silent fallback is attempted. A single pointer state machine distinguishes tap, 250 ms centre hold, outer-10% edge hold and movement beyond 12 CSS px without preventing native scroll. Only an explicit tap-pause or audible-policy rejection exposes central SVG play/sound controls; an actual guarded `play` event for the current video hides them. Holds never reveal controls. An activated centre hold preserves a pause lock for its original item/video/source/pointer sequence during scroll and iOS `pointercancel`; it resumes only on the actual touch end when that original item is active and was playing before the hold. Offline videos loop with `object-cover`, temporary edge holds use 2×, and scoped Reels styles suppress iOS callout/selection/drag without affecting the dashboard. Effective active selection is reversible and controls only pause/play while cards are partial. A full-screen commit requires observer ratio ≥ 0.999 plus 2 CSS px card/root geometry tolerance; only after it may the previous committed and fully invisible card reset offscreen. Thus a partial reversal resumes the saved position, while a post-commit return starts from 0 under existing seek guards. The lower Reels hierarchy is metadata overlay, non-seekable progress, then a safe-area-aware glass navigation; scoped backdrop blur is limited to that lower zone. The shared two-link navigation marks `/` (**Главная**) or `/offline` (**Рилсы**) active. Startup attempts guarded play at `HAVE_METADATA`/`loadedmetadata` rather than waiting for `canplay`; reset seeks still wait for current `seeked`. Stale-frame protection, playback generations and the previous/current/next three-source bound remain unchanged. iOS WebKit can briefly freeze or jump at 1×↔2× for AAC media; the MVP keeps normal audio and standard pitch preservation, accepts this platform limitation, and retains remux-first ingest rather than forcing short-GOP/no-B-frames transcodes. Re-downloading unchanged server media does not itself change that WebKit behavior.
- Post-iPhone hardening block 4A makes `/` the canonical dashboard and manifest `id`/`scope`/start route. It fetches every signed-cursor catalog page with duplicate/cursor-loop protection only while online, treats an offline catalog as neutral rather than an error, aborts and invalidates a pending request on connectivity loss, and reloads automatically on return to network. It sends only incomplete or failed records to the existing one-at-a-time queue, and reports storage and batch state as percentages only. Clear aborts the active queue, waits for its pump to settle, then removes only `offline-reels-media-v1` and IndexedDB records; a late download cannot repopulate the library. `/offline` removes summary, byte-size, technical-title and individual-delete presentation while preserving all Reels lifecycle guards. `/videos` remains an explicit precached legacy redirect to `/`; API video routes remain uncached. There is no runtime redirect from `/offline` to `/`: existing iOS installations must be reinstalled once after the manifest start-route migration, while precached `/` and `/offline` continue to support offline navigation. Future watched-retention policy is not implemented: a watched reel may later be removed locally after one hour and replaced when online, but a fully closed iOS PWA cannot guarantee background work.
- Post-iPhone hardening adds a controlled installed-PWA shell update. Serwist's supported `waiting` and `controlling` lifecycle events drive a compact Russian notification; no update is activated or page reloaded until the user selects **«Обновить»**. The action uses Serwist's message-based `SKIP_WAITING` path, reloads exactly once after `controllerchange`, and never accesses `offline-reels-media-v1` or the offline IndexedDB store.
- A manual smoke exposed the accepted PostgreSQL/MinIO inconsistency where metadata can outlive a deleted MinIO object. `VerticalVideoFeed` now treats a media `error` as terminal for that card: it clears the source and native loading state, shows a safe local message, and suppresses automatic source retries. Neighboring cards remain usable; no automatic PostgreSQL/MinIO reconciliation or backend fallback was added.

## Current open questions

- Exact synchronization strategy.
- Instagram session management.
- Media delivery architecture.
- Долгосрочная сохранность Cache Storage/IndexedDB и поведение при ограничении квоты iOS.

# Offline Reels

Personal application for preparing an Instagram Reels feed for offline viewing. The repository currently provides a backend-streamed multi-video feed, development MP4 seed flow, media normalization, and a local PWA library backed by IndexedDB, Cache Storage and one Service Worker. It now also contains Collector domain states and a database foundation, but has no Instagram runtime integration, authentication flow, browser worker, downloader, scheduler, watched state, Celery worker, or background downloading.

## Supported versions

| Component | Version |
| --- | --- |
| Node.js | 24.14.0 |
| npm | 11.9.0 |
| Next.js | 16.2.11 |
| Python | 3.14.3 |
| uv | 0.11.29 |
| PostgreSQL image | `postgres:17.10-alpine3.23` |
| Redis image | `redis:7.4.7-alpine3.21` |
| MinIO image | `minio/minio:RELEASE.2025-09-07T16-13-09Z-cpuv1` |

Node is pinned in [`.node-version`](.node-version); Python is pinned in [`apps/api/.python-version`](apps/api/.python-version). Dependency resolution is committed in `apps/web/package-lock.json` and `apps/api/uv.lock`.

## Quick start with Docker Compose

Docker Compose is the reproducible development entry point. Copy `.env.example` to `.env` if local values or ports need changing; never commit `.env`.

```powershell
make up
make ps
```

Open `http://localhost:3000`. The browser application calls the explicitly configured `NEXT_PUBLIC_API_BASE_URL` and displays the live Backend API state. The value is required and must be an absolute HTTP(S) URL without credentials, query, or fragment; the production client has no localhost fallback. Containers use internal URLs such as `postgres`, `redis`, and `minio`; `DATABASE_URL` and `REDIS_URL` in `.env.example` therefore target Docker service names. For local Docker development, the template uses `http://localhost:8000` deliberately as an environment value.

The API permits CORS only from `FRONTEND_ORIGIN` (default `http://localhost:3000`), never a wildcard.

## iPhone PWA staging and acceptance

Use the one-origin Tailscale Funnel staging workflow in
[`deploy/README.md`](deploy/README.md) for real-iPhone testing. Plain LAN HTTP
is not a reliable secure context for Service Worker, Cache Storage,
`navigator.storage`, or installed-PWA behavior on iOS.

Safari and the installed Home Screen PWA use separate offline-storage contexts.
Install the PWA first, then download videos from inside that installed PWA;
downloads made in a Safari tab do not populate the installed app library. The
completed acceptance also confirmed that MP4 codec parameters matter: VP9 in an
MP4 container failed on iPhone, while H.264 with `yuv420p` and `faststart`
played correctly. Media normalization now validates and prepares ingest media for that supported profile.

## Commands

When `make` is absent from `PATH`, set `$make` to the local GNU Make executable.

```powershell
$make = 'C:\path\to\make.exe'
& $make check
& $make config
& $make up
& $make ps
& $make migration-check
& $make minio-health
& $make down
```

`make check` performs frontend tests, linting, type checking and production build, then API Ruff and pytest checks. `make migration-check` runs Alembic downgrade to base and upgrade to the empty `0001_initial_schema` migration. `make minio-health` is diagnostic only: MinIO intentionally does not affect API readiness.

## Health endpoints

- `GET /health/live` — confirms only that FastAPI is running.
- `GET /health/ready` — confirms PostgreSQL and Redis; MinIO is deliberately excluded.
- `GET /health/minio` — diagnostic MinIO check, independent from readiness.

## Multi-video vertical feed

`GET /videos` uses signed cursor pagination. It accepts `limit` (default `10`, range `1`–`30`) and an optional opaque `cursor`; the web client requests five entries at a time. The response is:

```json
{
  "items": [],
  "next_cursor": "v1.opaque-payload.opaque-signature-or-null"
}
```

Videos are ordered by `created_at DESC, id DESC`. The cursor is an HMAC-SHA-256 signed transport value that carries the last item's timestamp and ID; clients must not parse it. An invalid cursor returns safe `400 invalid_cursor` without implementation details. `VIDEO_CURSOR_SECRET` is required, must have at least 32 characters, and must be a unique random secret outside local development. Never commit a production cursor secret.

`GET /videos/{id}` returns metadata and `GET /videos/{id}/stream` streams MP4 through the Backend API with one HTTP byte range. The browser never accesses MinIO directly.

Seed an existing local MP4 after starting Docker Compose:

```powershell
& $make seed-video FILE="C:\path\to\video.mp4"
& $make seed-videos DIR="C:\path\to\directory-with-mp4-files"
```

The command accepts only a non-empty `.mp4` file, copies it temporarily into the API container, hashes it in chunks, and uses `videos/<sha256>.mp4` as the idempotent object key. The temporary container file is removed even if the seed fails. Do not add MP4 files to Git.

`make seed-videos` processes regular `.mp4` files in deterministic name order. It continues after a failed file, always removes each temporary container file, groups results into created/restored, already existed and failed, and returns non-zero if any file failed. It is a development helper, not a user upload endpoint.

The canonical user route is `/`: a mobile dashboard that reads the complete paginated Backend catalog and starts one sequential offline batch. It displays network, storage, and batch state only as user-facing percentages. `/videos` remains a legacy redirect to `/` for old links and older shells; API paths such as `GET /videos` and `GET /videos/{id}/stream` are unchanged.

MinIO root credentials (`MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`) configure the MinIO server. Application credentials (`MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`) are used only by the API. They may be identical in `.env.example` for local development; production must use a separate least-privileged application user.

`make check` starts and tears down isolated integration infrastructure automatically. It uses a separate Compose project, PostgreSQL volume and MinIO bucket, so it never changes the dev database, dev volume or `offline-reels` bucket.

## Optional host-mode development

Start infrastructure with Compose, then use host URLs for API variables:

```powershell
npm --prefix apps/web ci
npm --prefix apps/web run dev
uv --directory apps/api sync --all-groups --frozen
$env:DATABASE_URL = 'postgresql+psycopg://offline_reels:change-me-local-postgres-password@localhost:5432/offline_reels'
$env:REDIS_URL = 'redis://localhost:6379/0'
$env:MINIO_ENDPOINT = 'http://localhost:9000'
uv --directory apps/api run uvicorn app.main:app --reload
```

## Offline PWA

The production build registers one Serwist worker at `/serwist/sw.js` with scope `/`. The manifest fixes `id`, `scope`, and `start_url` at `/`; `/`, `/offline`, the legacy `/videos` redirect, and `/manifest.webmanifest` are explicit revisioned shell entries. API and media routes remain outside shell caching. There is no runtime launch redirect: after changing the manifest start route, an existing iOS Home Screen installation must be reinstalled once. The precached shells still permit offline navigation between `/` and `/offline`. `offline-reels-media-v1` remains separate and `/offline-media/{id}` is served only from that local cache, without a Backend fallback. The dashboard does not request the server catalog while offline and resumes that request automatically when connectivity returns. The dashboard batch deduplicates catalog IDs, rejects cursor loops, skips valid completed records, retries failed records, and uses the existing one-at-a-time queue. Clear aborts the queue, waits for it to settle, then deletes only offline-owned media and IndexedDB metadata.

`/offline` selects the Reels-like mode of the shared `VerticalVideoFeed`: native controls are removed, looping `playsInline` video fills the card with `object-cover`, and the UI intentionally shows no individual technical title, file size, summary, or deletion action. A short central tap pauses and reveals accessible play/sound controls. Reels begins with sound enabled and honestly attempts audible startup; if iOS requires a first gesture, it remains unmuted and paused with the Play button available rather than silently falling back to muted playback. A 250 ms centre hold pauses only its original item for the lifetime of that physical touch: movement, native scrolling, and an iOS `pointercancel` do not resume it; release resumes it only when the same item is active and was playing before the hold. Outer 10% edge zones use a 250 ms hold for temporary 2× playback, and neither hold exposes tap controls. Movement beyond 12 CSS px yields to native vertical scroll-snap. The active threshold controls only pause/play during a reversible drag; a full-screen commit prepares the prior card at 0:00 offscreen. Reels-only scoped styles suppress iOS callout, selection and media drag without preventing scrolling. The MVP retains normal audio and standard `preservesPitch`; on iOS WebKit a short frame freeze or clock jump can occur at the temporary 1×/2× boundary, an accepted platform limitation.

When Serwist reports a waiting shell update, the installed PWA shows a safe-area-aware Russian notification. The user must select **«Обновить»**; only then does the app send Serwist's supported `SKIP_WAITING` message, wait for `controllerchange`, and reload once. This does not clear the media cache or IndexedDB. The dashboard uses `navigator.storage.estimate()` only for a percentage and keeps browser storage details out of the user interface.

The lower visual layout uses shared CSS variables: the floating navigation reserves its safe-area plus a bounded adaptive lift. Reels keeps a transparent non-interactive progress layer and one fixed shared glass backdrop that continues behind progress, the pill and safe area. That layer alone uses scoped backdrop blur, saturation and a translucent gradient with an opaque fallback; it is never applied to the video element or playback lifecycle.

## Security

`.env.example` contains templates only. Do not commit real passwords, tokens, Instagram cookies, sessions, or production data. The client communicates only with the Backend API; external Instagram integration remains outside this bootstrap.

## Instagram Collector foundation

The backend has durable Collector domain contracts, an Alembic schema and a
fixture-only sequential orchestration core. Fixture mode uses deterministic
canonical Reel candidates, a temporary local source directory and SQLite; it
never makes a network request or accesses an Instagram session. Its ordering is
strict: pause, validate and publish a source, then atomically commit Reel,
normalization-job and run-item state before one advance is permitted. A
database failure after a newly published fixture object triggers best-effort
compensation of that object only; a pre-existing object is never removed.

Run the isolated fixture command with a bounded target and allowlisted scenario:

```powershell
uv --directory apps/api run python -m app.scripts.run_instagram_collector_fixture --scenario happy --target 3
```

The current catalog remains unchanged: only a future `ready` canonical MP4
(H.264/yuv420p/AAC) may be linked to `videos`. There is no production Instagram
connection, browser adapter, downloader, source-storage runtime or normalizer
worker yet. The validated browser/download spike remains a separate local
research project. See [ADR 007](docs/adr/007-instagram-collector-pipeline.md).

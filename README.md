# Offline Reels

Personal application for preparing an Instagram Reels feed for offline viewing. The repository currently provides a backend-streamed multi-video feed, development MP4 seed flow, and a local PWA library backed by IndexedDB, Cache Storage and one Service Worker. It has no Instagram integration, authentication, recommendations, watched state, Celery worker, background downloading, or transcoding.

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
played correctly. Media normalization is the next functional stage.

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

The `/videos` page is a native vertical scroll-snap feed. `IntersectionObserver` keeps ratios for every mounted item and selects the active item with a deterministic feed-center tie-breaker; a requestAnimationFrame-throttled scroll fallback covers browsers that report only partial observer entries. Only the active player is asked to play, while all others are paused. Playback begins muted, and the accessible mute button controls the React session state for all mounted players. Only the active player and its next neighbor receive stream URLs (`preload="auto"` and `preload="metadata"` respectively); all other mounted players use `preload="none"` without a source. No video virtualization, offline caching, service worker or carousel library is included in this task.

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

The production build registers one Serwist worker at `/serwist/sw.js` with scope `/`. The manifest opens installed applications at `/offline`; its app shell is precached separately from `offline-reels-media-v1`, which holds downloaded MP4 responses. `/offline-media/{id}` is same-origin and served only from the local media cache; it has no Backend fallback. When Serwist reports a waiting shell update, the installed PWA shows a safe-area-aware Russian notification. The user must select **«Обновить»**; only then does the app send Serwist's supported `SKIP_WAITING` message, wait for `controllerchange`, and reload once. This does not clear the media cache or IndexedDB. The offline page shows exact library bytes from IndexedDB, approximate origin usage/quota when supported, and whether `navigator.storage.persisted()` reports persistent storage. This is a diagnostic only: the app never requests persistence automatically and iOS may still evict data.

## Security

`.env.example` contains templates only. Do not commit real passwords, tokens, Instagram cookies, sessions, or production data. The client communicates only with the Backend API; external Instagram integration remains outside this bootstrap.

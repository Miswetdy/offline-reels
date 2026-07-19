# Offline Reels

Personal application for preparing an Instagram Reels feed for offline viewing. This repository currently contains the production bootstrap only: it has no Instagram integration, media downloading, authentication, feed business logic, Celery worker, service worker, or offline caching.

## Supported versions

| Component | Version |
| --- | --- |
| Node.js | 24.14.0 |
| npm | 11.9.0 |
| Next.js | 16.2.10 |
| Python | 3.14.3 |
| uv | 0.11.29 |
| PostgreSQL image | `postgres:17.10-alpine3.23` |
| Redis image | `redis:7.4.7-alpine3.21` |
| MinIO image | `minio/minio:RELEASE.2025-09-07T16-13-09Z-cpuv1` |

Node is pinned in [`.node-version`](.node-version); Python is pinned in [`apps/api/.python-version`](apps/api/.python-version). Dependency resolution is committed in `apps/web/package-lock.json` and `apps/api/uv.lock`.

## Quick start with Docker Compose

Docker Compose is the reproducible development entry point. Copy `.env.example` to `.env` if local values or ports need changing; never commit `.env`.

```powershell
& 'C:\Users\Misha\AppData\Local\Microsoft\WinGet\Links\make.exe' up
& 'C:\Users\Misha\AppData\Local\Microsoft\WinGet\Links\make.exe' ps
```

Open `http://localhost:3000`. The browser application calls `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`) and displays the live Backend API state. It never uses the internal Docker host name. Containers use internal URLs such as `postgres`, `redis`, and `minio`; `DATABASE_URL` and `REDIS_URL` in `.env.example` therefore target Docker service names. For a host-run API, override them to use `localhost`.

The API permits CORS only from `FRONTEND_ORIGIN` (default `http://localhost:3000`), never a wildcard.

## Commands

When `make` is absent from `PATH`, use the verified absolute executable shown below.

```powershell
$make = 'C:\Users\Misha\AppData\Local\Microsoft\WinGet\Links\make.exe'
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

## Security

`.env.example` contains templates only. Do not commit real passwords, tokens, Instagram cookies, sessions, or production data. The client communicates only with the Backend API; external Instagram integration remains outside this bootstrap.

# Стек

| Область | Реализация |
| --- | --- |
| Frontend | Next.js, React, TypeScript, Tailwind, Serwist PWA |
| Локальные данные | Cache Storage, IndexedDB через idb |
| Backend | Python, FastAPI, SQLAlchemy, Alembic |
| Данные/файлы | PostgreSQL, Redis, MinIO |
| Collector | Playwright, Chrome for Testing, yt-dlp |
| Media | ffmpeg, ffprobe |
| Развёртывание | Docker Compose, Caddy; Tailscale для staging HTTPS |
| Проверки | pytest, Ruff, Vitest, Testing Library, Playwright E2E |

Node `24.14.0`, npm `11.9.0`, Python `3.14.3`.
Источники версий: [Node](../.node-version), [Python](../apps/api/.python-version),
[web package](../apps/web/package.json), [API project](../apps/api/pyproject.toml).
Точное разрешение зависимостей хранится в package-lock.json и uv.lock;
версии images/browser — в Dockerfile и Compose.

Collector dependencies устанавливаются отдельным extra/image; API не содержит
Chromium. Normalizer — отдельный процесс. Celery и scheduler не реализованы.

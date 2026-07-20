# Status

## Current stage

Multi-video vertical feed (TASK-004).

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

## Current focus

TASK-004 is implemented and manually smoke-tested with real Instagram Reels in Chrome and Yandex Browser. Measure long-session memory behavior on a real iPhone before considering virtualization.

## Next step

Before offline-client delivery, plan validation of iOS quotas, long-term persistence, a large offline library, feed memory behavior and the safe browser-compatible media format for ingestion.

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
- Web dependency security triage updated Vitest to 4.1.10 and removed its critical development-only advisory. The moderate PostCSS advisory remains open through Next.js 16.2.10's nested PostCSS 8.4.31; no unsafe audit fix or Next.js downgrade was applied.
- TASK-003 streams video through Backend API rather than presigned storage URLs. Integration tests use isolated PostgreSQL and MinIO infrastructure.
- TASK-003 was validated end-to-end: idempotent seed uploaded the 13,864,238-byte spike MP4, `/videos` returned one record, HTTP streaming returned `200` and `206`, multipart Range returned `416`, and the video remained available after `make down`/`make up`.
- TASK-004 uses `created_at DESC, id DESC` keyset pagination with an HMAC-SHA-256 signed opaque cursor. The cursor secret is required at runtime and never belongs in Git.
- TASK-004 keeps loaded video elements mounted while validating native scroll-snap UX. To avoid Chromium open-ended Range downloads from every mounted element, only the active player and its next neighbor receive stream URLs; all remaining cards stay mounted without a source. Full DOM virtualization remains a future real-device performance task.
- The active-player selection retains the latest `IntersectionObserver` ratio for every feed card, resolves ties by the feed center, and has a requestAnimationFrame-throttled scroll fallback for browsers that emit only partial observer callback batches.
- Real Instagram Reels passed the manual TASK-004 feed smoke scenario in Chrome and Yandex Browser. The earlier issue was limited to some third-party test MP4 encodings, not pagination, active-player selection, the media window, Range streaming or the Backend API. A future ingestion task must define media validation and, if needed, normalization or transcoding for a safe MVP format; no transcoding was added to TASK-004.

## Current open questions

- Exact synchronization strategy.
- Instagram session management.
- Media delivery architecture.
- Долгосрочная сохранность Cache Storage/IndexedDB и поведение при ограничении квоты iOS.

# Status

## Current stage

First video vertical slice (TASK-003).

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

## Current focus

TASK-003 is complete and validated with the existing sample MP4.

## Next step

Plan the next agreed production capability. Before offline-client delivery, plan validation of iOS quotas, long-term persistence, and a large offline library.

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

## Current open questions

- Exact synchronization strategy.
- Instagram session management.
- Media delivery architecture.
- Долгосрочная сохранность Cache Storage/IndexedDB и поведение при ограничении квоты iOS.

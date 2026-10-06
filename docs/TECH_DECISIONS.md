# Действующие решения

iPhone PWA — единственная целевая платформа MVP. Сервер готовит видео;
клиент работает через Backend и воспроизводит локальные файлы.
Текущее поведение — в [архитектуре](ARCHITECTURE.md), готовность — в [STATUS](STATUS.md).

ADR фиксируют причины и ограничения решений, а не журнал выполнения.
Устаревшие эксперименты и заменённые варианты доступны в Git; номера не перенумерованы.

- [001 — Cache Storage + IndexedDB](adr/001-cache-storage-indexeddb-offline-video.md)
- [002 — Видео через Backend API](adr/002-api-video-streaming.md)
- [003 — Каталог с keyset pagination](adr/003-keyset-video-feed-pagination.md)
- [004 — Согласованность локальной библиотеки](adr/004-offline-library-local-storage-foundation.md)
- [005 — Один Serwist worker для PWA](adr/005-serwist-turbopack-application-shell.md)
- [006 — Локальная media route](adr/006-service-worker-offline-media-route.md)
- [007 — Collector и durable media pipeline](adr/007-instagram-collector-pipeline.md)
- [009 — Отдельный Collector image](adr/009-server-ready-linux-collector-container.md)
- [010 — Ручной login через серверный Chromium](adr/010-secure-mobile-instagram-login-browser.md)
- [011 — Отдельный normalizer worker](adr/011-instagram-normalization-worker.md)
- [012 — Защищённое управление](adr/012-protected-instagram-management-control-plane.md)
- [013 — Локальный запас принадлежит устройству](adr/013-local-reserve-device-reports.md)
- [014 — Просмотр после свайпа и локальное удаление](adr/014-viewed-reel-lifecycle.md)
- [015 — Linux Chromium sandbox](adr/015-hardened-linux-chromium-collector.md)
- [016 — Stage 10 single-origin ingress](adr/016-stage10-single-origin-ingress.md)
- [017 — Linux login и общий профиль](adr/017-hardened-stage10-instagram-login.md)
- [019 — Operator handoff в том же Chromium process](adr/019-same-process-collector-operator-handoff.md)
- [022 — Следующий Reel из authenticated embedded JSON](adr/022-embedded-reels-feed-candidate-queue.md)

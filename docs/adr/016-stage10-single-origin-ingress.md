# ADR 016: Stage 10 single-origin ingress

Принято. Отдельный Caddy слушает `127.0.0.1:13080`; production Caddy
в Stage 10 отключён. Публичный HTTPS proxy направляет запросы только сюда.

Без rewrite: `/videos`, `/videos/*`, `/health/*`, `/api/*` идут в API;
`/connect/*`, `/remote/*` — login gateway; `/handoff/*` — handoff gateway;
остальное — Next.js. Frontend route/shell `/videos` удалены.
Media не кэшируется ingress; Range semantics принадлежат API.

NEXT_PUBLIC_API_BASE_URL, FRONTEND_ORIGIN и MANAGEMENT_ORIGIN используют
один HTTPS origin без /api suffix. Изменение public build URL требует rebuild web.
Старые installed PWA должны принять обновление worker.
Serve — tailnet-only; Funnel публикует приложение в интернете.

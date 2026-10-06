# ADR 003: Каталог с keyset pagination

Принято. `GET /videos` возвращает `items` и `next_cursor`;
порядок — `created_at DESC, id DESC`, без offset drift.

Курсор непрозрачен для клиента, подписан HMAC-SHA-256 и проверяется сервером.
`VIDEO_CURSOR_SECRET` обязателен и должен быть уникальным случайным секретом.
Dashboard читает все страницы с защитой от повторов ID и cursor loops.

Пользовательские страницы — `/` и `/offline`; frontend `/videos` удалён.
Плеер использует native scroll-snap и previous/current/next source window,
а не прежний online feed этой ранней итерации.

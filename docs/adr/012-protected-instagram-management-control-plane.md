# ADR 012: Защищённое управление

Принято. Operator CLI создаёт одноразовый pairing code; DB хранит его hash.
Устройство получает Secure HttpOnly SameSite cookie.
Mutations требуют точного HTTPS Host/Origin, CSRF и DB-backed idempotency;
pairing защищён rate limits.

FastAPI создаёт/читает/отменяет durable commands, но не запускает browser,
Collector или normalizer. Отмена кооперативна и сохраняет committed Reels.

Login capability возвращается лишь один раз и не сохраняется в replay record.
Management/login responses — no-store; frontend не хранит admin secret.
Токены и raw reason codes не попадают в UI/logs.
Auto-collection settings не означают scheduler: `scheduler_active=false`.

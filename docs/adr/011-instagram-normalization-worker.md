# ADR 011: Отдельный normalizer worker

Принято. Browser-free процесс получает PostgreSQL job через
FOR UPDATE SKIP LOCKED и UUID lease. FastAPI его не запускает.

Committed source проходит ffprobe/full decode, remux или transcode в MP4:
H.264/yuv420p, AAC при наличии audio, faststart. Attempt-owned staging
публикуется в immutable SHA-256 final key до DB-транзакции ready/video/job.
Source удаляется только после commit; неудачная очистка остаётся для reconcile.

Staging не виден каталогу. Existing final objects проверяются и не затираются;
compensation ограничена объектом текущей попытки без durable reference.
Retries ограничены тремя попытками; expired leases и cleanup обрабатывает reconcile.

Команда `app.scripts.run_instagram_normalizer_worker` поддерживает
`--once`, `--limit`, `--daemon`, `--status`, `--verify`, `--reconcile`.

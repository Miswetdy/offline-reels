# ADR 022: Следующий Reel из authenticated embedded JSON

Принято в текущем коде; source-only Linux live-приёмка остаётся открытой.
Виртуализированная лента не даёт надёжной связи между свайпом и canonical ID,
поэтому видимая смена видео больше не является источником следующего ID.

После fixed /reels/ navigation provider читает только explicit
application/json и application/ld+json scripts authenticated документа.
Ограничены payload/tree traversal, очередь (32) и session memory IDs (64).
Допускаются code/shortcode/media_code только под media-shaped ancestry
и после strict canonical validator; arbitrary DOM attributes/inline JS исключены.

После durable commit live adapter резервирует embedded-кандидата без
swipe/keyboard/wheel. Если очередь пуста, выполняет один fixed refresh
на переход; старые pending entries сбрасываются, bounded known-ID memory
сохраняется. Initial и reserved кандидаты помечаются использованными.
При отсутствии нового кандидата — AUTHENTICATED_FEED_EXHAUSTED.

Это очередь рекомендаций, а не доказательство ID конкретной видимой карточки.
Provider также наблюдает GraphQL для diagnostic/legacy paths; Web API остаётся
aggregate-only диагностикой и не поставляет кандидатов.
Queue IDs живут в памяти; принятые Reel сохраняются обычным durable pipeline.
Логи не содержат ID, URLs, cookies, response bodies или DOM text.

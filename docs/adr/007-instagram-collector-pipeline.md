# ADR 007: Collector и durable media pipeline

Принято. Instagram-интеграция изолирована за feed/downloader/validator/storage
interfaces. Collector — отдельный последовательный процесс, не код запуска API.

1. Проверить сессию/canonical shortcode; приостановить текущее видео.
2. Скачать session-first через минимальный CookieJar в памяти.
3. Валидировать и опубликовать source.
4. Одной DB-транзакцией записать Reel source_ready, job и run item.
5. Только после durable commit получить следующий кандидат.
6. Отдельный normalizer публикует ready canonical MP4 для каталога.

Shortcode — глобальная внешняя identity; runs/items определяют принадлежность
аккаунту. Уже durable источник не скачивается заново. При DB-сбое можно
компенсировать только объект, созданный текущей попыткой.

Checkpoint/challenge/reauth останавливают автоматизацию.
Не сохранять raw exceptions, HTML, media URLs, auth headers и cookies.
Persistent browser profile — секретный серверный ресурс с exclusive lock.
Текущий источник следующих кандидатов — [ADR 022](022-embedded-reels-feed-candidate-queue.md).

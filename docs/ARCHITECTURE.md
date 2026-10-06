# Архитектура

## Поток данных

```text
Instagram → Collector → MinIO source + PostgreSQL job
                      → normalizer → MinIO canonical MP4 + ready catalog
PWA ← Backend API ← PostgreSQL / MinIO
 ↓
Cache Storage (MP4) + IndexedDB (состояние) → offline Service Worker → плеер
```

Клиент работает через Backend API. Instagram-профили и cookies принадлежат
серверной интеграции; frontend не обращается к Instagram или MinIO напрямую.
Защищённый remote-browser gateway передаёт пользовательский ввод при входе.

## Границы сервисов

| Компонент | Ответственность |
| --- | --- |
| `apps/web` | Next.js PWA, dashboard, local download queue, offline playback |
| `apps/api/app/api` | Каталог/stream и защищённые management-команды |
| `instagram/collector` | Последовательный engine и заменяемые feed/download/storage adapters |
| `instagram/normalizer` | Отдельный browser-free worker подготовки media |
| `apps/login-browser`, login gateway | Ручной вход и серверный persistent profile |
| PostgreSQL | Accounts, runs/items, Reels/jobs, videos, sessions, reports, views |
| MinIO | Исходные и нормализованные файлы |
| Redis | Runtime coordination; не очередь Celery |

API не запускает Collector или normalizer. Management API записывает durable
команды; отдельно запущенные процессы забирают работу. Scheduler отсутствует.

## Collector и normalizer

Collector проверяет сессию и canonical-кандидата, приостанавливает текущий
ролик, скачивает через session-first yt-dlp с временным CookieJar в памяти,
валидирует источник и публикует его. Только после общей DB-транзакции
Reel `source_ready` + normalization job + run item разрешён следующий кандидат.
При DB-сбое компенсируется лишь объект, созданный текущей попыткой.

Текущий live adapter берёт последующие ID из ограниченной embedded JSON
очереди текущей authenticated Reels-страницы. После исчерпания выполняется
одно фиксированное обновление страницы на переход; отсутствие нового ID
завершает run с `AUTHENTICATED_FEED_EXHAUSTED`. ID не привязывается к видимой
карточке. Старые gesture adapters остаются для fixtures/диагностики.
Контракт источника — [ADR 022](adr/022-embedded-reels-feed-candidate-queue.md).

Normalizer использует PostgreSQL lease и `FOR UPDATE SKIP LOCKED`,
проверяет ffprobe и полный decode, затем remux/transcode в MP4:
H.264, yuv420p, AAC при наличии аудио, faststart.
Публикация через attempt-owned staging и SHA-256 final key предшествует
транзакции `ready`/video/job. Очистка source выполняется после commit.
Retries ограничены; reconciliation восстанавливает expired leases и cleanup.

## API и доступ

Каталог использует HMAC-подписанный keyset cursor `created_at DESC, id DESC`.
Stream поддерживает GET/HEAD, один byte range и ответы 200/206/416.
MinIO остаётся внутренним; его недоступность проверяется отдельно от readiness.

Устройство подключается одноразовым operator pairing code. Management session
использует Secure HttpOnly cookie, точный Host/Origin, CSRF, idempotency
и DB-backed rate limits. Ответы управления/login имеют `no-store`.
Отмена кооперативна и сохраняет уже закоммиченные источники.

## Локальная библиотека и просмотр

Один Serwist worker обслуживает offline shell `/` и `/offline`.
`/videos` принадлежит API; API/management/streams не кэшируются как shell.
`/offline-media/{id}` читает только локальный media cache, включая single Range,
без fallback на Backend. Обработчик Range материализует целый файл в памяти.

Downloader пишет cache, проверяет размер/type, затем фиксирует completed
metadata в IndexedDB. Reconciliation исключает битые/прерванные записи
и удаляет orphan media. Очистка ждёт остановки очереди.
Плеер держит источники только предыдущего, текущего и следующего ролика.

Завершённый пользовательский свайп A → B создаёт первый viewed event,
tombstone и outbox атомарно. Через час удаляется только локальный MP4;
удаление откладывается, пока этот ролик активен. Серверный first-view
идемпотентен и исключает Reel из каталога аккаунта. Tombstones запрещают
повторную загрузку; глобальные видео и другие аккаунты не удаляются.

Reserve settings и фактические локальные файлы принадлежат устройству.
Backend хранит только безопасный отчёт. Автопополнение выключено compile-time;
закрытая iOS PWA не обязана выполнять фоновые задачи.

## Linux и login

Stage 10 Caddy слушает только `127.0.0.1:13080`. Без изменения путей:
`/videos*`, `/health/*`, `/api/*` → API; `/connect/*`, `/remote/*` → login
gateway; `/handoff/*` → handoff gateway; остальное → web.

Login и Collector используют один pinned Chrome for Testing, один профиль
аккаунта и atomic lock. Они не работают с профилем одновременно.
Контейнеры non-root, cap-drop ALL, no-new-privileges, read-only rootfs,
ограниченные seccomp/AppArmor. VNC/CDP/controller и profile не публикуются.

Проверка входа делает не более одной verification-навигации на сессию.
Account/challenge страницы остаются для ручного решения; готовность означает
проверенную Reels boundary. После входа браузер закрывается, профиль сохраняется.

Опциональный handoff показывает тот же процесс Collector через одноразовый
защищённый relay. До подтверждения нет collection input/download/persistence;
expiry/cancel закрывают процесс. См. [ADR 019](adr/019-same-process-collector-operator-handoff.md).

Операционные команды — в [runbook](operations/stage-10-linux-staging.md);
подтверждённая готовность — только в [STATUS](STATUS.md).

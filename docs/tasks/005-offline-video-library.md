# TASK-005 — Offline sync и локальная видеотека

## Статус

Planned

## Контекст

На предыдущих этапах реализованы:

- backend API со списком видео;
- хранение метаданных в PostgreSQL;
- хранение MP4 в MinIO;
- HTTP Range streaming;
- cursor pagination;
- вертикальная scroll-snap лента;
- autoplay активного ролика;
- ограничение media window до активного и следующего видео;
- ручная проверка реальных Instagram Reels в Chrome и Яндекс Браузере.

Сейчас лента полностью зависит от доступности backend и интернета. После отключения сети пользователь не может закрыть приложение, открыть его повторно и продолжить просмотр ранее загруженных роликов.

В TASK-001 отдельно подтверждено на реальном iPhone, что PWA может:

- сохранять MP4 в Cache Storage;
- сохранять метаданные в IndexedDB;
- переживать закрытие и повторный запуск;
- открываться в авиарежиме;
- воспроизводить локально сохранённое видео.

В TASK-005 необходимо перенести проверенный подход из spike в основное приложение и реализовать полноценный офлайн-сценарий для нескольких роликов.

---

## Цель

Реализовать в основном PWA-приложении устойчивую локальную видеотеку, которая позволяет:

1. получить список роликов с backend;
2. скачать выбранные ролики на устройство;
3. сохранить MP4 и метаданные между перезапусками приложения;
4. открыть установленную PWA без интернета;
5. посмотреть скачанные ролики в существующей вертикальной ленте;
6. удалить отдельный ролик;
7. полностью очистить локальную библиотеку;
8. увидеть количество скачанных роликов и занимаемый ими объём.

Главный технический вопрос этапа:

> Может ли основное PWA-приложение надёжно хранить и воспроизводить несколько полноразмерных Instagram Reels без подключения к интернету?

---

## Ожидаемый пользовательский сценарий

### Онлайн

1. Пользователь открывает страницу `/videos`.
2. Приложение получает онлайн-ленту через backend API.
3. Пользователь нажимает «Скачать следующие 5».
4. Приложение рассчитывает ожидаемый объём загрузки.
5. Выбранные ролики ставятся в локальную очередь.
6. Ролики скачиваются последовательно, по одному.
7. Пользователь видит:
   - текущий статус;
   - прогресс активной загрузки;
   - количество скачанных роликов;
   - количество роликов в очереди;
   - ошибки и возможность повторить загрузку.
8. Полностью скачанные ролики отмечаются как доступные офлайн.

### Офлайн

1. Пользователь полностью закрывает PWA.
2. Отключает интернет или включает авиарежим.
3. Повторно открывает установленную PWA.
4. Application shell загружается без сети.
5. Приложение читает локальный каталог из IndexedDB.
6. Пользователь открывает офлайн-ленту.
7. В ленте отображаются только полностью скачанные ролики.
8. Видео воспроизводятся из Cache Storage без обращения к backend.
9. Вертикальная прокрутка, autoplay, pause и mute продолжают работать.
10. Пользователь может удалить один ролик или очистить всю библиотеку.

---

## Критерий успеха

TASK-005 считается успешно выполненной, если минимум пять реальных Instagram Reels:

- полностью скачиваются на устройство;
- скачиваются последовательно, а не параллельно;
- не дублируются при повторной постановке в очередь;
- сохраняются после закрытия и повторного запуска PWA;
- воспроизводятся в авиарежиме;
- доступны в существующей вертикальной scroll-snap ленте;
- могут быть удалены вместе с локальными метаданными и медиаданными.

Обязательная финальная проверка:

- desktop Chrome;
- реальный iPhone;
- установленная PWA;
- авиарежим;
- полный перезапуск приложения после загрузки роликов.

---

# Архитектурное решение

## Источники данных

Приложение должно явно различать два режима работы.

### Онлайн-режим

Источники:

- backend API — метаданные роликов;
- `/videos/{id}/stream` — медиаданные.

### Офлайн-режим

Источники:

- IndexedDB — локальный каталог, статусы и метаданные;
- Cache Storage — полностью скачанные MP4;
- Service Worker — application shell и локальная раздача media.

---

## Разделение ответственности

### IndexedDB

IndexedDB является источником истины для локальной видеотеки и хранит:

- метаданные ролика;
- статус загрузки;
- состояние очереди;
- ожидаемый и загруженный размер;
- время завершения загрузки;
- cache key;
- информацию о последней ошибке;
- время последнего просмотра.

IndexedDB не должна хранить большие MP4 Blob целиком.

### Cache Storage

Cache Storage хранит:

- только полностью скачанные MP4;
- один стабильный cache entry на один video id;
- Response с корректным `Content-Type`;
- данные отдельно от application shell cache.

### React state

React state хранит только временное UI-состояние:

- progress активной загрузки;
- состояние кнопок;
- текущие ошибки интерфейса;
- выбранный режим ленты;
- отображаемые данные очереди.

React state не является источником истины для локальной библиотеки.

---

# Локальная модель данных

Создать версионированную IndexedDB-базу.

Предлагаемое имя:

```text
offline-reels
```

Предлагаемый object store:

```text
offline-videos
```

Минимальная модель:

```ts
type OfflineVideoStatus =
  | "queued"
  | "downloading"
  | "completed"
  | "failed";

type OfflineVideoRecord = {
  id: string;
  title: string;
  contentType: string;
  byteSize: number;
  createdAt: string;

  status: OfflineVideoStatus;

  downloadedBytes: number;
  downloadedAt: string | null;

  cacheKey: string | null;

  lastErrorCode: string | null;
  lastErrorMessage: string | null;
  failedAt: string | null;

  lastWatchedAt: string | null;
  updatedAt: string;
};
```

Допускается добавить технические поля, если они действительно нужны для:

- безопасных миграций;
- сортировки;
- startup reconciliation;
- восстановления прерванных загрузок;
- версионирования локальной схемы.

---

## Инварианты локальных данных

Запись может иметь статус `completed` только если:

- Cache Storage содержит соответствующий MP4;
- cached response полностью читается;
- фактический размер совпадает с ожидаемым `byteSize`;
- content type относится к допустимому видеоформату;
- `cacheKey` заполнен.

Если IndexedDB и Cache Storage расходятся, приложение должно восстановить консистентность:

- `completed` без cache entry переводится в `failed` либо удаляется;
- cache entry с неправильным размером удаляется;
- orphan cache entry без metadata удаляется во время controlled cleanup;
- незавершённая загрузка после закрытия приложения не считается completed.

---

# Cache Storage

Использовать отдельный версионированный media cache.

Предлагаемое имя:

```text
offline-reels-media-v1
```

Application shell и MP4 не должны храниться в одном cache.

Стабильный cache key:

```text
/offline-media/{videoId}
```

Cache key должен быть:

- same-origin;
- детерминированным;
- независимым от backend cursor;
- независимым от временного или подписанного URL;
- безопасно формируемым только из валидного video id.

Не сохранять в IndexedDB `blob:` URLs, потому что они не переживают перезапуск страницы.

---

## Требования к media cache

- Один `videoId` соответствует одному cache entry.
- В media cache должны попадать только полностью скачанные файлы.
- Частично скачанный MP4 не должен появляться под финальным cache key.
- Повторное скачивание completed-видео не создаёт дубль.
- Удаление ролика удаляет и metadata, и cache entry.
- Очистка библиотеки удаляет media cache, но не application shell.
- Cache entry с неожиданным `Content-Type` не считается валидным.
- Cache entry с неправильным размером не считается валидным.

---

# Очередь загрузки

## Ограничение параллелизма

Для MVP:

```text
concurrency = 1
```

Одновременно скачивается только один ролик.

Причины:

- предсказуемое использование памяти;
- снижение нагрузки на устройство;
- снижение нагрузки на backend;
- более простая обработка ошибок;
- понятный пользовательский прогресс;
- снижение риска нескольких крупных параллельных загрузок.

---

## Состояния очереди

Успешный сценарий:

```text
queued
  ↓
downloading
  ↓
completed
```

Ошибка и повтор:

```text
queued
  ↓
downloading
  ↓
failed
  ↓
queued
  ↓
downloading
```

---

## Требования к очереди

- Повторное добавление одного video id не создаёт вторую задачу.
- Completed-видео не скачивается повторно без отдельного явного действия.
- Failed-видео можно повторить.
- После ошибки одного ролика очередь продолжает следующий.
- Активная загрузка отменяется через `AbortController`.
- Отменённая загрузка не считается completed.
- Unmount React-компонента не должен создавать второй worker.
- В приложении не должно существовать несколько параллельных queue workers.
- После перезапуска записи со статусом `downloading` не должны зависать навсегда.
- Startup recovery должен перевести такие записи в безопасное состояние.
- Очередь работает только пока приложение открыто.
- TASK-005 не обещает продолжение скачивания после полного закрытия PWA.

Предпочтительная startup policy:

```text
stale downloading → failed
```

с отдельным кодом ошибки, указывающим, что загрузка была прервана закрытием приложения.

---

# Алгоритм скачивания одного видео

Для каждого ролика:

1. Проверить, нет ли валидной completed-копии.
2. Создать или обновить IndexedDB record со статусом `queued`.
3. Перевести запись в `downloading`.
4. Выполнить полный запрос к backend stream endpoint.
5. Не использовать частичный Range-запрос для offline download.
6. Проверить:
   - успешный HTTP status;
   - наличие response body;
   - ожидаемый `Content-Type`;
   - `Content-Length`, если он присутствует;
   - соответствие backend metadata;
   - допустимый размер.
7. Потоково получить всё тело ответа.
8. Записать полный Response в Cache Storage.
9. Повторно прочитать cache entry.
10. Проверить размер и заголовки cached response.
11. Только после успешной cache verification выставить `completed`.
12. При любой ошибке:
    - не оставлять ложный completed status;
    - удалить возможный некорректный cache entry;
    - сохранить безопасный error code;
    - сохранить пользовательское сообщение;
    - продолжить очередь.

---

## Атомарность

В браузере нет общей транзакции между IndexedDB и Cache Storage.

Использовать компенсационный алгоритм:

```text
set downloading
→ download full response
→ validate response
→ write cache
→ verify cache
→ mark metadata completed
```

При ошибке после записи cache, но до сохранения completed metadata:

- удалить cache entry немедленно;
- либо восстановить состояние во время startup reconciliation.

Не выставлять `completed` до подтверждённой записи и проверки cached response.

---

# Прогресс загрузки

При наличии `ReadableStream` необходимо получать progress потоково.

Показывать:

- загруженные байты текущего файла;
- ожидаемый размер текущего файла;
- процент текущего файла;
- количество завершённых файлов;
- количество файлов в очереди;
- общий ожидаемый размер batch;
- общий загруженный размер batch.

Не хранить каждый chunk в React state.

Обновления progress должны быть throttled, чтобы не вызывать render на каждый сетевой chunk.

Не собирать весь крупный ролик в один дополнительный `ArrayBuffer` или `Blob`, если это приводит к двойному хранению файла в оперативной памяти.

Если точный byte progress невозможно надёжно реализовать для целевых браузеров без существенного усложнения:

- загрузка должна продолжать работать;
- UI показывает indeterminate progress;
- progress на уровне файлов остаётся обязательным;
- решение и ограничение фиксируются в ADR или `docs/RISKS.md`.

---

# Валидация ответа

Перед сохранением MP4 проверить:

- HTTP status;
- наличие body;
- `Content-Type`;
- `Content-Length`, если доступен;
- фактически полученный размер;
- соответствие ожидаемому `byteSize`;
- отсутствие явно неполного ответа.

Не считать расширение `.mp4` гарантией browser compatibility.

В TASK-005 не реализовывать transcoding, но использовать нормализованные error codes.

Предлагаемые error codes:

```ts
type OfflineDownloadErrorCode =
  | "network_error"
  | "http_error"
  | "unsupported_content_type"
  | "content_length_mismatch"
  | "storage_quota_exceeded"
  | "cache_write_failed"
  | "cache_validation_failed"
  | "download_aborted"
  | "download_interrupted"
  | "cache_entry_missing"
  | "unknown_error";
```

Пользователь не должен видеть stack trace или внутренние технические детали.

---

# Выбор роликов для загрузки

На странице `/videos` добавить минимальное управление:

```text
Скачать следующие 5
```

Для MVP:

```text
N = 5
```

Поведение:

- выбор начинается с текущего активного ролика либо с первой ещё не скачанной записи;
- уже completed-видео не добавляются повторно;
- queued и downloading-видео не дублируются;
- перед запуском показывается или рассчитывается ожидаемый общий размер;
- выбранные ролики ставятся в последовательную очередь.

Для каждой карточки добавить минимальный статус:

- не скачано;
- в очереди;
- скачивается;
- скачано;
- ошибка;
- повторить;
- удалить локальную копию.

Не строить финальный интерфейс библиотеки. UI должен быть аккуратным, но функциональным и минимальным.

---

# Офлайн-лента

Добавить отдельную страницу или явно выделенный режим, предпочтительно:

```text
/offline
```

Офлайн-лента использует только записи:

```text
status = completed
```

из IndexedDB.

Media URL:

```text
/offline-media/{videoId}
```

---

## Требования к офлайн-ленте

- Не обращаться к backend за списком роликов.
- Не обращаться к backend за MP4.
- Показывать только валидные completed-записи.
- Использовать существующую vertical scroll-snap логику.
- Сохранить active + next media window.
- Одновременно держать `src` максимум у активного и следующего ролика.
- Сохранить autoplay активного ролика.
- Ставить предыдущий ролик на паузу.
- Сохранить единое muted state.
- Корректно работать после полного перезапуска PWA.
- Показывать понятный empty state, если локальная библиотека пуста.
- Не показывать бесконечный loader при отсутствии сети.

Не копировать всю логику `video-list.tsx` во второй независимый компонент.

Желательно выделить общие части:

- feed item model;
- media source resolver;
- active item logic;
- vertical feed component;
- online/offline data source.

Не переписывать рабочую TASK-004 реализацию целиком без необходимости.

---

# Service Worker и application shell

Основное приложение должно открываться без сети после хотя бы одного успешного онлайн-запуска.

Service Worker должен кешировать минимальный application shell, необходимый для:

- запуска приложения;
- открытия `/offline`;
- загрузки JavaScript;
- загрузки CSS;
- загрузки локальных assets;
- чтения IndexedDB;
- обращения к Cache Storage;
- отображения офлайн-ленты.

Не использовать агрессивный catch-all cache для всех запросов.

Не кешировать автоматически:

- backend API responses;
- `/videos/{id}/stream`;
- любые произвольные cross-origin responses;
- ошибки backend;
- временные URLs.

Application shell cache и offline media cache должны иметь разные имена и версии.

Service Worker update flow не должен навсегда оставлять пользователя на старой версии приложения.

---

# Offline media route

Service Worker должен обрабатывать запросы:

```text
GET /offline-media/{videoId}
```

и возвращать соответствующий MP4 из media cache.

Требования:

- валидировать формат `videoId`;
- возвращать корректный `Content-Type`;
- возвращать `404`, если cache entry отсутствует;
- не обращаться к backend;
- использовать стабильный same-origin URL;
- корректно работать после reload;
- корректно работать в авиарежиме.

---

# Range для offline media

Необходимо проверить, отправляет ли браузер Range-запросы к `/offline-media/{videoId}`.

Если обычный cached Response не обеспечивает корректный seeking автоматически, Service Worker должен обслуживать одиночный HTTP Range из полного локального файла.

Минимально поддержать:

- полный GET;
- `bytes=start-end`;
- `bytes=start-`;
- `bytes=-suffix`;
- `206 Partial Content`;
- `416 Range Not Satisfiable`;
- `Content-Range`;
- `Content-Length`;
- `Accept-Ranges: bytes`.

При Range-запросе:

- использовать только локальный cached MP4;
- не обращаться к backend;
- корректно обрабатывать inclusive end;
- корректно обрезать диапазон концом файла;
- корректно обрабатывать некорректный или недостижимый Range.

Не добавлять поддержку multipart ranges в TASK-005.

---

# Online/offline detection

Использовать:

```ts
navigator.onLine
```

только как UI hint.

Не считать его гарантией доступности backend.

Подписаться на события:

```text
online
offline
```

При потере сети:

- не показывать бесконечный loader;
- предложить перейти в офлайн-библиотеку;
- не удалять текущие данные;
- не запускать бесконечные retries.

При восстановлении сети:

- не перезагружать страницу автоматически;
- разрешить ручной retry;
- не запускать скрытую массовую загрузку без действия пользователя.

---

# Управление локальным хранилищем

Использовать:

```ts
navigator.storage.estimate()
```

если API доступен.

Показывать:

- количество completed-видео;
- сумму `byteSize` completed-записей;
- приблизительный `usage`;
- приблизительный `quota`;
- приблизительно доступное пространство.

Перед batch download:

1. Рассчитать ожидаемый размер выбранных роликов.
2. Получить storage estimate.
3. Добавить разумный safety margin.
4. Если места явно недостаточно:
   - не начинать загрузку автоматически;
   - показать понятное сообщение.
5. Если Storage Estimate API недоступен:
   - не блокировать загрузку;
   - предупредить, что браузер сам управляет квотой.

Не считать `quota - usage` гарантированно доступным местом.

При наличии поддержки вызвать:

```ts
navigator.storage.persist()
```

Запрос persistent storage должен быть best-effort.

Отказ браузера не должен ломать приложение.

---

# Quota errors

При `QuotaExceededError`:

- текущая загрузка получает статус `failed`;
- частичный или некорректный cache entry удаляется;
- очередь не должна бесконечно повторять ошибку;
- пользователь получает понятное сообщение;
- следующие загрузки не должны запускаться автоматически, если свободного места явно нет.

---

# Удаление одного ролика

Удаление локальной копии должно:

1. отменить загрузку, если она активна;
2. убрать ролик из очереди;
3. остановить локальное воспроизведение;
4. удалить media cache entry;
5. удалить IndexedDB record либо локальные offline-поля;
6. обновить online и offline UI;
7. не затронуть серверную запись;
8. не удалить MP4 из MinIO.

Если один из шагов завершается ошибкой, приложение не должно оставлять ложный completed state.

---

# Очистка библиотеки

Добавить явное действие:

```text
Очистить офлайн-библиотеку
```

Перед выполнением запросить подтверждение.

Очистка должна:

- отменить активную загрузку;
- остановить queue worker;
- удалить все offline video records;
- удалить media cache текущей версии;
- сбросить queue states;
- обновить UI;
- не удалить application shell cache;
- не удалить серверные видео;
- не удалить PostgreSQL или MinIO данные.

---

# Startup reconciliation

При запуске приложения выполнить безопасную проверку согласованности IndexedDB и Cache Storage.

Проверить:

- записи со статусом `downloading`;
- completed metadata без cache entry;
- cache entry с неправильным размером;
- cache entry с неожиданным `Content-Type`;
- orphan cache entries без metadata;
- записи неизвестной или устаревшей схемы.

Минимальная политика:

```text
stale downloading
→ failed(download_interrupted)

completed без cache
→ failed(cache_entry_missing)

invalid cache
→ удалить cache
→ failed(cache_validation_failed)

valid completed
→ оставить

orphan cache
→ удалить controlled cleanup
```

Reconciliation не должен надолго блокировать первый render.

UI может показывать локальный loading state, пока проверяются данные, но не бесконечный spinner.

---

# Работа с видеоформатами

TASK-004 показала, что расширение `.mp4` не гарантирует одинаковую browser compatibility.

Реальные Instagram Reels прошли ручной smoke в Chrome и Яндекс Браузере.

В TASK-005 не реализовывать:

- `ffmpeg`;
- `ffprobe`;
- transcoding;
- codec normalization.

Но заложить будущий риск и отдельную задачу:

- server-side media validation;
- проверка codec/profile/pixel format;
- нормализация входящих файлов;
- при необходимости transcoding в:
  - MP4;
  - H.264/AVC;
  - `yuv420p`;
  - AAC.

---

# Требования к структуре кода

Не размещать всю offline-логику в `video-list.tsx`.

Предпочтительная структура:

```text
apps/web/
  lib/
    offline/
      types.ts
      db.ts
      cache.ts
      downloader.ts
      download-queue.ts
      reconciliation.ts
      storage-estimate.ts
      media-url.ts

  hooks/
    use-offline-library.ts
    use-download-queue.ts

  components/
    video-list.tsx
    offline-download-controls.tsx
    offline-library-summary.tsx

  app/
    offline/
      page.tsx
```

Фактические имена можно изменить в соответствии с текущими conventions проекта.

Обязанности:

- `types.ts` — domain types и error codes;
- `db.ts` — IndexedDB schema, migrations и CRUD;
- `cache.ts` — Cache Storage operations;
- `downloader.ts` — скачивание одного ролика;
- `download-queue.ts` — concurrency=1 и state transitions;
- `reconciliation.ts` — startup consistency recovery;
- `storage-estimate.ts` — quota, usage и persist;
- `media-url.ts` — online/offline media URLs;
- hooks — orchestration;
- components — UI.

Требования:

- browser-only APIs не должны вызываться во время SSR;
- React-компоненты не содержат низкоуровневые IndexedDB-транзакции;
- зависимости направлены от UI к domain/storage abstractions;
- ошибки типизированы;
- cleanup listeners и AbortController обязателен;
- не добавлять тяжёлую state-management библиотеку без необходимости.

---

# Зависимости

Перед добавлением новой зависимости:

1. Проверить, нельзя ли решить задачу browser APIs и небольшими внутренними abstractions.
2. Проверить актуальное состояние библиотеки.
3. Проверить security advisories.
4. Зафиксировать точную версию.
5. Объяснить необходимость.

Допускается небольшая typed-обёртка для IndexedDB, например `idb`, если она:

- активно поддерживается;
- типизирована;
- уменьшает количество низкоуровневого кода;
- не скрывает критичную reconciliation logic;
- не добавляет тяжёлый runtime.

Не добавлять крупные offline-first frameworks.

---

# Безопасность и надёжность

- Не сохранять Instagram credentials или cookies.
- Не сохранять secrets в IndexedDB, Cache Storage или localStorage.
- Cache keys не должны содержать токены.
- Не логировать response body.
- Не отображать backend stack traces пользователю.
- Не рендерить ошибки как HTML.
- Не использовать `dangerouslySetInnerHTML`.
- Валидировать `videoId` в Service Worker.
- Не принимать arbitrary cache key из пользовательского ввода.
- Не сохранять response с неожиданным `Content-Type`.
- Не сохранять failed или partial download как completed.
- Отменять активные запросы через `AbortController`.
- Очищать listeners, observers, subscriptions и RAF.
- Не создавать два queue workers.
- Обрабатывать отсутствие IndexedDB, Cache Storage и StorageManager APIs.
- Не обращаться к `window`, `navigator`, `indexedDB` или `caches` во время SSR.

---

# UI

Не строить финальный дизайн.

Нужен аккуратный функциональный интерфейс для проверки механики.

## На `/videos`

Добавить:

- индикатор состояния сети;
- кнопку скачивания текущего видео;
- кнопку «Скачать следующие 5»;
- статус локальной доступности ролика;
- progress активной загрузки;
- количество элементов в очереди;
- retry failed-загрузки;
- удаление локальной копии;
- ссылку или кнопку перехода в `/offline`.

## На `/offline`

Показывать:

- количество скачанных роликов;
- занимаемый объём;
- storage estimate, если доступен;
- вертикальную офлайн-ленту;
- удаление одного ролика;
- очистку всей библиотеки;
- empty state;
- ошибку повреждённого локального состояния;
- возможность вернуться в онлайн-ленту.

---

# Testing

## Unit tests

Покрыть:

- построение cache key;
- IndexedDB CRUD;
- schema upgrade;
- повторный upsert;
- status transitions;
- duplicate enqueue;
- concurrency=1;
- retry;
- abort;
- stale downloading recovery;
- нормализацию ошибок;
- batch size calculation;
- storage safety check;
- удаление одного ролика;
- очистку библиотеки;
- completed metadata без cache;
- invalid cache size;
- orphan cache cleanup;
- отсутствие browser APIs.

---

## Downloader tests

Покрыть:

- успешную полную загрузку;
- сетевую ошибку;
- HTTP error;
- пустой body;
- неожиданный `Content-Type`;
- `Content-Length` mismatch;
- фактический size mismatch;
- abort;
- quota error;
- cache write failure;
- cache verification failure;
- metadata update failure после cache write;
- cleanup после ошибки;
- `completed` выставляется только в самом конце.

---

## Queue tests

Покрыть:

- одновременно выполняется только один job;
- второй job ждёт первого;
- следующий job запускается после completed;
- следующий job запускается после failed;
- duplicate enqueue игнорируется;
- completed item не скачивается повторно;
- retry failed item;
- abort active item;
- queue не создаёт два worker;
- queue корректно останавливается;
- reload recovery не оставляет downloading навсегда.

---

## Cache tests

Покрыть:

- успешную запись;
- cache hit;
- cache miss;
- удаление;
- очистку media cache;
- проверку размера;
- проверку content type;
- partial download не остаётся completed;
- metadata says completed, cache отсутствует;
- orphan cache entry;
- разные версии cache не смешиваются.

---

## Service Worker tests

Покрыть:

- application shell navigation fallback;
- media cache и shell cache разделены;
- `/offline-media/{id}` cache hit;
- `/offline-media/{id}` cache miss;
- invalid video id;
- полный response;
- bounded Range;
- open-ended Range;
- suffix Range;
- clipped end Range;
- invalid Range;
- `416`;
- корректный `Content-Range`;
- корректный `Content-Length`;
- `Accept-Ranges: bytes`;
- отсутствие backend request при offline media playback.

---

## Component tests

Покрыть:

- download current;
- download next 5;
- queued state;
- downloading state;
- completed state;
- failed state;
- retry;
- progress;
- offline indicator;
- offline empty state;
- library summary;
- delete one;
- clear all confirmation;
- API failure не ломает offline feed;
- download failure не ломает online feed;
- active + next media window остаётся максимум два `src`;
- offline URLs корректно подставляются в feed.

---

## E2E / browser smoke

Если текущая инфраструктура позволяет без чрезмерного расширения scope, добавить browser-level сценарий:

1. открыть приложение онлайн;
2. скачать два небольших fixture MP4;
3. дождаться completed;
4. проверить IndexedDB;
5. проверить media cache;
6. перезагрузить страницу;
7. эмулировать offline;
8. открыть `/offline`;
9. воспроизвести cached video;
10. проверить reload в offline;
11. удалить ролик;
12. убедиться, что он больше не доступен.

Если Playwright отсутствует:

- сначала описать минимальный план его введения;
- не добавлять сложную E2E-инфраструктуру без согласования;
- ручной desktop и iPhone smoke остаются обязательными.

Не добавлять крупные MP4 fixtures в Git.

Для автоматических тестов использовать маленькие контролируемые fixture-файлы, если они допустимы по размеру и лицензии, либо генерируемые/мокированные responses.

---

# Manual acceptance test

## Desktop Chrome

1. Запустить чистый stack.
2. Открыть `/videos`.
3. Скачать минимум пять реальных Instagram Reels.
4. Убедиться, что загрузки идут строго последовательно.
5. Проверить progress.
6. Проверить отсутствие дублей при повторном нажатии.
7. Перезагрузить страницу.
8. Проверить сохранение статусов.
9. Открыть `/offline`.
10. Включить Offline в DevTools.
11. Полностью перезагрузить страницу.
12. Воспроизвести все скачанные ролики.
13. Проверить вертикальный scroll-snap.
14. Проверить autoplay.
15. Проверить pause предыдущего ролика.
16. Проверить mute.
17. Проверить seeking.
18. Удалить один ролик.
19. Проверить его отсутствие в IndexedDB и Cache Storage.
20. Очистить библиотеку.
21. Проверить, что application shell продолжает открываться без сети.

---

## Реальный iPhone PWA

1. Собрать production PWA.
2. Разместить приложение по HTTPS.
3. Открыть сайт в Safari.
4. Добавить приложение на главный экран.
5. Открыть установленную PWA онлайн.
6. Скачать минимум пять реальных Instagram Reels.
7. Дождаться completed для всех роликов.
8. Зафиксировать общий размер локальной библиотеки.
9. Полностью закрыть PWA.
10. Включить авиарежим.
11. Повторно открыть PWA с главного экрана.
12. Открыть `/offline`.
13. Воспроизвести все скачанные ролики.
14. Проверить scroll-snap.
15. Проверить autoplay и mute.
16. Проверить seeking.
17. Несколько раз полностью закрыть и открыть PWA.
18. Убедиться, что данные сохраняются.
19. Удалить один ролик.
20. Повторно открыть PWA и убедиться, что ролик не вернулся.
21. Очистить всю библиотеку.
22. Проверить пустое состояние.

---

# Наблюдаемость

В development допустимо контролируемое логирование событий:

- queue item queued;
- queue item started;
- download completed;
- download failed;
- download aborted;
- cache verification failed;
- reconciliation action;
- quota warning.

Не оставлять шумный `console.log` в production.

Использовать существующую logging abstraction либо небольшой dev-only logger.

Не логировать:

- MP4 body;
- cookies;
- токены;
- секреты;
- чувствительные URL-параметры.

---

# Документация

Обновить:

- `README.md`;
- `docs/ARCHITECTURE.md`;
- `docs/STATUS.md`;
- `docs/RISKS.md`;
- при необходимости создать ADR по offline storage architecture.

ADR должен зафиксировать:

- почему metadata хранится в IndexedDB;
- почему MP4 хранится в Cache Storage;
- почему используются synthetic same-origin media URLs;
- почему application shell и media разделены;
- почему очередь имеет `concurrency=1`;
- почему background downloading не входит в MVP;
- почему нет общей транзакции между IndexedDB и Cache Storage;
- как работает compensation и reconciliation;
- ограничения iOS storage eviction;
- отсутствие гарантии вечного хранения browser storage;
- почему transcoding не входит в TASK-005.

---

# Non-goals

В TASK-005 не входят:

- Instagram authentication;
- Instagram Collector;
- автоматическое получение персональной ленты;
- server-side downloader Instagram;
- фоновые загрузки при закрытой PWA;
- гарантированная загрузка при заблокированном iPhone;
- обязательный Background Sync;
- push notifications;
- HLS;
- DASH;
- transcoding;
- `ffmpeg`;
- `ffprobe`;
- codec normalization;
- DRM;
- синхронизация между устройствами;
- пользовательские аккаунты;
- облачная история просмотров;
- автоматический LRU eviction;
- сложные storage policies;
- финальный UI;
- лайки;
- комментарии;
- публикация;
- native iOS или Android application.

---

# Backend changes

Backend API, pagination и streaming endpoint по возможности не менять.

Допускаются только минимальные изменения, если для корректной offline-загрузки доказанно необходимы:

- CORS headers;
- `Content-Length`;
- `Content-Type`;
- отдельный безопасный full-download endpoint.

Перед добавлением нового endpoint необходимо доказать, что существующий `/stream` не подходит.

Не дублировать MP4 в другом server-side storage.

Не добавлять server-side offline queue.

---

# Риски

## iOS storage eviction

Safari/iOS может удалить browser storage при нехватке места или системной очистке.

Митигация:

- не обещать вечное хранение;
- показывать фактическое состояние библиотеки;
- валидировать cache при запуске;
- уметь повторно скачать ролики;
- использовать `navigator.storage.persist()` best-effort.

---

## Ограниченный background execution

PWA не может надёжно продолжать крупную загрузку после полного закрытия приложения.

Митигация:

- явно сообщать, что приложение нужно держать открытым;
- сохранять состояние очереди;
- переводить interrupted items в failed;
- разрешать ручной retry;
- не заявлять background download как готовую функцию.

---

## Большие файлы

Некоторые Reels могут занимать десятки мегабайт.

Митигация:

- последовательная очередь;
- storage estimate;
- batch size preview;
- progress;
- возможность отмены;
- отсутствие параллельных загрузок.

---

## Несогласованность IndexedDB и Cache Storage

Нет общей транзакции между двумя browser storage.

Митигация:

- cache verification перед completed metadata;
- compensating cleanup;
- startup reconciliation;
- тестирование промежуточных failure states.

---

## Browser compatibility

Поведение Service Worker, Cache Storage, autoplay, Range и quota может различаться.

Митигация:

- не полагаться на один браузер;
- graceful fallback;
- ручная проверка desktop Chrome;
- обязательная проверка реального iPhone;
- использование реальных Instagram MP4.

---

# Acceptance criteria

TASK-005 считается завершённой, если:

- [ ] создана версионированная IndexedDB-схема;
- [ ] создан отдельный media cache;
- [ ] application shell cache отделён от media cache;
- [ ] реализована последовательная download queue;
- [ ] одновременно выполняется максимум одна загрузка;
- [ ] минимум пять роликов можно поставить в очередь;
- [ ] отображается progress;
- [ ] duplicate enqueue не создаёт дубль;
- [ ] partial download не становится completed;
- [ ] failed download можно повторить;
- [ ] active download можно отменить;
- [ ] stale downloading восстанавливается после reload;
- [ ] completed-видео переживают reload;
- [ ] IndexedDB переживает полный перезапуск;
- [ ] Cache Storage переживает полный перезапуск;
- [ ] основная PWA запускается без сети;
- [ ] `/offline` открывается без backend;
- [ ] офлайн-лента показывает только completed-видео;
- [ ] MP4 воспроизводятся без backend;
- [ ] seeking работает офлайн;
- [ ] Range обслуживается локально при необходимости;
- [ ] autoplay, pause и mute работают;
- [ ] media window остаётся максимум два `src`;
- [ ] один ролик можно удалить;
- [ ] всю библиотеку можно очистить;
- [ ] показывается количество скачанных роликов;
- [ ] показывается занимаемый объём;
- [ ] используется `navigator.storage.estimate()`, если доступен;
- [ ] quota errors обрабатываются;
- [ ] startup reconciliation исправляет неконсистентные записи;
- [ ] online feed TASK-004 не сломана;
- [ ] backend pagination не сломана;
- [ ] backend streaming не сломан;
- [ ] frontend tests проходят;
- [ ] backend tests проходят;
- [ ] lint проходит;
- [ ] typecheck проходит;
- [ ] production build проходит;
- [ ] desktop offline smoke пройден;
- [ ] реальный iPhone airplane-mode smoke пройден;
- [ ] документация обновлена;
- [ ] известные ограничения зафиксированы;
- [ ] в Git нет MP4, `.env`, browser profiles и storage dumps.

---

# Команды проверки

Перед завершением выполнить:

```bash
make config
make check
make migration-check
git diff --check
npm audit
npm audit --omit=dev
```

Если будет добавлен отдельный E2E command:

- включить его в `make check`;
- либо явно задокументировать отдельную команду и причину.

---

# Порядок реализации

Не реализовывать TASK-005 одним большим изменением.

Предлагаемый порядок:

1. Изучить TASK-001 spike и текущую архитектуру.
2. Изучить текущую PWA и Service Worker конфигурацию.
3. Подготовить implementation plan.
4. Зафиксировать IndexedDB schema.
5. Зафиксировать cache naming/versioning.
6. Реализовать storage primitives.
7. Реализовать downloader одного ролика.
8. Реализовать queue `concurrency=1`.
9. Реализовать startup reconciliation.
10. Добавить download controls на `/videos`.
11. Добавить `/offline`.
12. Переиспользовать существующую vertical feed.
13. Настроить offline application shell.
14. Добавить offline media route и Range.
15. Добавить storage summary и deletion.
16. Добавить unit и component tests.
17. Добавить доступный browser-level smoke.
18. Провести desktop manual smoke.
19. Подготовить HTTPS deployment.
20. Провести iPhone airplane-mode smoke.
21. Обновить документацию.
22. Провести cleanup и финальный review.

---

# Ограничения для Codex

Перед написанием кода:

1. Изучить:
   - `AGENTS.md`;
   - `README.md`;
   - `docs/ARCHITECTURE.md`;
   - `docs/STATUS.md`;
   - `docs/RISKS.md`;
   - TASK-001 spike;
   - TASK-004 implementation;
   - текущую PWA-конфигурацию;
   - текущую frontend test infrastructure.
2. Проверить актуальную документацию используемых browser APIs и библиотек.
3. Подготовить подробный implementation plan.
4. Указать все файлы, которые предлагается создать или изменить.
5. Описать спорные архитектурные решения.
6. Найти противоречия между TASK-005 и текущей архитектурой.
7. Дождаться подтверждения плана перед реализацией.

Во время реализации:

- не менять backend streaming без доказанной необходимости;
- не менять backend pagination;
- не добавлять Instagram integration;
- не добавлять transcoding;
- не добавлять browser-specific хаки без подтверждённой причины;
- не удалять существующие dev-данные;
- не запускать `docker compose down -v`;
- не добавлять `.env`;
- не добавлять MP4;
- не добавлять browser profiles;
- не добавлять Cache Storage dumps;
- не добавлять IndexedDB dumps;
- не делать commit;
- не делать push.

После каждого логического блока:

- запускать релевантные тесты;
- сообщать результат;
- обновлять `docs/STATUS.md`, только если блок реально завершён;
- не переходить к следующему крупному блоку без понятного результата текущего.

Финальный commit и push выполняет пользователь.

---

# Definition of Done

Перед завершением TASK-005:

- проверить весь diff;
- удалить временный debug-код;
- удалить временные `console.log`;
- проверить cleanup observers, listeners, RAF и AbortController;
- убедиться, что нет абсолютных локальных путей;
- убедиться, что нет UUID тестовых видео;
- убедиться, что нет секретов;
- убедиться, что MP4 не попали в Git;
- убедиться, что `.env` не отслеживается;
- выполнить все проверки проекта;
- выполнить `git diff --check`;
- обновить task status;
- обновить project status;
- зафиксировать known limitations;
- оставить контейнеры в понятном состоянии;
- не выполнять commit и push без ручного подтверждения пользователя.

## Implementation status

TASK-005 Block 6.1 hardens the existing local-library persistence boundary without adding background download or changing playback lifecycle. Reconciliation is idempotent: only a validated `completed` metadata record owns a media cache entry; interrupted downloads, missing/invalid/zero-byte media and orphan responses are invalidated or removed locally. Downloader completion remains ordered as Cache Storage write, cache validation, then IndexedDB `completed`; cache-first delete/clear operations use reconciliation as compensation if metadata cleanup fails. Browser storage and quota errors remain typed, user-safe states. Real-device quota, eviction and long-session acceptance remain outside this block.

TASK-005 Block 6.2 hardens playback runtime behavior without adding a new media delivery mechanism. The shared feed keeps sources only on active and next items, clears/pause inactive media, pauses all videos during `visibilitychange`/`pagehide`/`pageshow`, and does not auto-start playback on return. It keeps an active selection valid after local delete/clear mutations. `/offline` requires an active Service Worker controller, handles `controllerchange` without reload, and reports an unavailable Service Worker API as a controlled state. Local media failures remain per-item and never trigger Backend fallback or automatic retry. The current single-range handler reads one full cached MP4 into worker memory per request; iPhone lifecycle, seek and memory acceptance are deferred to Block 6.3.

TASK-005 Block 6.3 acceptance ran through one HTTPS Tailscale Funnel origin, with `/api` as the public API prefix. The client has no implicit production localhost API origin and local offline media remains same-origin. The run established that Safari and the installed Home Screen PWA use separate offline-storage contexts, so users must install before downloading media. It also confirmed a codec constraint: VP9 in MP4 failed on iPhone, while H.264 with `yuv420p` and `faststart` played. Media normalization and a post-normalization repeat acceptance are the next stages.

When a catalog item exists but its media request fails—for example, after an object was removed from MinIO while PostgreSQL metadata remains—the player now enters a terminal controlled error state. It clears its source and native loading state, excludes that item from automatic source reassignment, and leaves the rest of the vertical feed usable. This is a frontend containment policy only; automatic PostgreSQL/MinIO reconciliation remains out of scope.

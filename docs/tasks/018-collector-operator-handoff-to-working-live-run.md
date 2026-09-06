# TASK-018: Operator handoff в процессе Collector до рабочего live-run

**Статус:** в работе. Выполнение этапов ведётся непрерывно до итогового
результата; не завершать работу между диагностикой, реализацией, deploy и
bounded VPS-проверками.

## Цель

Получить работающий server-side Collector: один live-run `3/3` с двумя
подтверждёнными переходами, тремя durable источниками и валидными MP4. После
этого подготовить переход к отдельной PWA/iPhone acceptance на лимите `50`.

## Текущая картина

- Collector успешно открывает persistent Instagram profile, получает первый
  Reel, скачивает и durable-коммитит его.
- Переходы блокирует интерактивный слой: focusable inherited `role=button` с
  modal/dialog ancestor перехватывает оба endpoint; video ниже top hit stack.
- JSON-gate исправен: DOM-смена или произвольный JSON не засчитываются без
  stable media identity и нового post-action authenticated JSON с другим
  canonical Reel.
- Passive modal-lifecycle diagnostic подтвердил, что blocker устойчив после
  двух bounded wait. Alignment экрана/scale/viewport с login browser также не
  изменил результат.
- Private login viewer и Collector используют persistent profile mount, но это
  не доказывает идентичность live UI context: сейчас это разные Chromium
  процессы.

## Решение: one-time operator handoff

Нужно добавить отдельный opt-in handoff flow, в котором **один и тот же
Collector Chromium process** проходит три состояния:

1. Запускается с текущим non-root sandbox, persistent account profile и
   существующим presentation contract.
2. Останавливается перед первым feed input и через одноразовый signed gateway
   показывает оператору только private VNC relay этого процесса.
3. После явного operator-confirmation продолжает тот же bounded live 3/3 run,
   без перезапуска Chromium, смены profile, переноса cookies или повторной
   навигации.

Оператор вручную решает только видимый dialog. Collector не кликает modal,
не извлекает его содержимое и не получает права на account/safety UI.

## Обязательные ограничения

- Нет публичных VNC, CDP, browser-control, profile или cookie endpoint.
- Gateway доступен лишь по одноразовой ссылке, signed HttpOnly session cookie,
  fixed HTTPS origin/Host и короткому TTL.
- Handoff container получает только private VNC relay; CDP остаётся loopback.
- До operator confirmation Collector не делает touch/click/keyboard/wheel,
  download, DB/Redis/MinIO mutation.
- После confirmation сохраняются direct two-endpoint video hit gate,
  native-touch constraint, JSON-gate, один retry и исходные deadlines.
- Не писать DOM text, dialog text, URLs, cookies, tokens, reel IDs,
  coordinates, screenshots или VNC data в logs/results.
- При TTL, cancellation, disconnect или timeout: закрыть browser, освободить
  profile lock, не запускать collection и вернуть fail-closed reason code.

## План непрерывного выполнения

1. Реализовать Collector handoff state machine и private relay boundary.
2. Добавить Compose profile с non-root/AppArmor/seccomp/no-new-privileges,
   VNC только во внутренней сети и без data-plane до confirmation.
3. Расширить gateway только одноразовым handoff viewer и confirm/cancel API.
4. Добавить unit/Chromium/Compose security tests: TTL, origin, no public
   control, no input before confirmation, same-process continuation.
5. Запустить tests, Ruff, diff-check, secret audit; обновить STATUS/RISKS/
   ARCHITECTURE и ADR при изменении boundary; commit и push.
6. Развернуть на Stage 10, создать one-time handoff link и довести operator
   viewer до connected state.
7. Дождаться только ручного закрытия/разрешения dialog и explicit confirm.
   Это единственная допустимая внешняя пауза; после неё не завершать задачу.
8. Продолжить тот же process bounded live 3/3, проверить два canonical
   перехода, ffprobe/decode, MinIO/PostgreSQL state и отсутствие temp files.
9. Если 3/3 успешен, реализовать/проверить PWA command flow и Stage-10 limit
   `50`, затем выполнить iPhone online sync и offline playback acceptance.

## Критерии результата

### Server Collector

- 3/3 новых Reel в одном run, два подтверждённых перехода.
- Каждый переход: stable new central media identity + новый post-action
  authenticated feed JSON с другим canonical Reel.
- Все файлы H.264/AAC, ffprobe/decode PASS; нет temporary artifacts.
- При любом сбое — только durable commits, корректный terminal reason.

### PWA/iPhone (после server 3/3)

- Нажатие `Загрузить Reels` создаёт новый command, а не использует старый
  каталог.
- Stage-10 PWA хранит максимум 50 новых Reel.
- После отключения сети PWA с домашнего экрана открывает и воспроизводит
  локальные файлы без Backend/Instagram.

## Серверный контекст

Stage 10 VPS: `associated-teal`, Ubuntu 24.04, `171.22.119.246`, user
`offline-reels`, repository `/srv/offline-reels`. Основные сервисы Stage 10
должны оставаться healthy. Секреты, `.env`, одноразовые URL и profile files не
включать в документацию, commit или отчёт.

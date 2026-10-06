# TASK-018: стабильный Linux Collector и live-приёмка

**Статус:** в работе. Текущий runtime — Stage 10; [runbook](../operations/stage-10-linux-staging.md).

## Цель

Один bounded run: три новых durable Reel source, два перехода к новым
кандидатам, валидные файлы и чистое завершение. После этого — подготовка
свежей коллекции и отдельная PWA/iPhone-приёмка на лимите 50.

## Текущее решение

Handoff уже реализован: оператор может вручную завершить Instagram dialog
в том же Chromium process, затем явно продолжить сбор.
Переход по свайпу не гарантировал canonical ID (`TRANSITION_FAILED`).

Последующий live advance теперь получает проверенный embedded JSON кандидат
без жестов. Очередь ограничена, ID дедуплицируются; один fixed `/reels/` refresh
на переход может добавить новые ID. Без кандидата — `AUTHENTICATED_FEED_EXHAUSTED`.
Source-only Linux acceptance и успешный 3/3 остаются открытыми.

Последние login fixes предотвращают повторную verification-навигацию
и показывают пользователю страницы ручного подтверждения.

## Порядок продолжения

1. Проверить deployment текущей ревизии, login и освобождение profile lock.
2. Выполнить `identity-diagnostic --source-only`: два последовательных новых
   кандидата без downloader, PostgreSQL/Redis/MinIO adapters.
3. При успехе провести bounded 3/3 с post-run проверкой durable state,
   объектов, валидности источников и удаления attempt-owned временных файлов.
4. Запустить normalizer и проверить ready MP4, полный decode и API Range.
5. Завершить PWA fresh-collection flow: текущий dashboard может скачать
   существующий ready catalog; это не доказывает новый collection command.
6. После 3/3 подготовить Stage 10 target/device cap 50 и пройти
   [iPhone checklist](../acceptance/iphone.md) со свежими Reels.

## Ограничения

- До успешного 3/3 не расширять target/retry limits ради обхода ошибки.
- Сохранять durable-commit-before-advance и строгую canonical validation.
- Не считать видимую смену видео доказательством canonical identity.
- Не обходить CAPTCHA/challenge; account dialogs решает пользователь.
- Не экспортировать cookies/profile и не публиковать VNC/CDP/controller.
- Non-root Chromium с sandbox/seccomp/AppArmor; profile lock обязателен.
- В результатах только безопасные счётчики/reason codes, без идентификаторов,
  секретов, URLs, DOM/response bodies или screenshots аккаунта.

Итоговый успех: новая коллекция реально скачивается в установленную PWA,
не превышает 50 Reel и воспроизводится после отключения сети.

# TASK-017: Диагностика жизненного цикла modal-layer в Instagram Collector

**Статус:** выполнено на Stage 10; live-сбор по-прежнему не разрешён.

## Цель

Установить, почему в Chromium-контексте Collector над центральным Reel остаётся
интерактивный слой с `role=button` под `dialog/modal`, даже после ручного
действия оператора в private viewer. Диагностика должна выяснить жизненный цикл
слоя, а не обходить, нажимать или отключать его.

## Установленные факты

- Bounded Stage-10 run на target `3` после connected private viewer сохранил
  один новый durable source, но дал `0` подтверждённых переходов и terminal
  `TRANSITION_FAILED`.
- Выбранный central `<video>` был available и in-viewport, но не получил
  прямой hit-test на обоих endpoint будущего swipe.
- Верхний hit имеет focusable inherited `role=button` и modal/dialog ancestor;
  video находится ниже него в point stack. Поэтому native touch корректно не
  отправлялся.
- Наблюдался post-action authenticated feed JSON, но не было одновременно
  stable new media identity и другого canonical Reel. JSON-gate правильно не
  засчитал переход.
- В private viewer оператор увидел connected remote browser, открыл Instagram
  и вручную обработал видимый dialog. Это не является доказательством того,
  что UI state идентичен отдельному запуску Collector.

## Границы и запреты

- Не отправлять touch, click, keyboard, wheel либо JavaScript `scrollBy` в
  observed control/modal layer.
- Не ослаблять требование двух прямых video hit-test endpoint и не заменять
  canonical post-action JSON URL/DOM/старым JSON-ответом.
- Не делать Instagram API-вызовы, неограниченные retry, скачивание, публикацию
  MinIO, DB-коммит или нормализацию в diagnostic-only запуске.
- Не записывать cookies, токены, URL, response body, DOM-текст, селекторы,
  координаты, скриншоты, media identity, reel ID или атрибуты элементов.
- Не менять target `3`, byte/deadline/retry limits или переходить к acceptance
  на `50` до выполнения критериев ниже.

## Требуемая реализация

1. Добавить отдельный явный operator-only режим `modal-lifecycle-diagnostic`.
   Он открывает уже подготовленный профиль, переходит к личному Reels feed и
   завершает работу без collection pipeline и browser input.
2. Выполнить фиксированную последовательность пассивных наблюдений:

   - после запуска Chromium;
   - после открытия Reels feed;
   - после bounded ожидания готовности;
   - непосредственно перед тем местом, где обычный Collector выбрал бы input
     target;
   - после второго bounded ожидания без input.

   Число наблюдений и каждое ожидание должны иметь константные конечные
   пределы. Никакого polling до бесконечности.
3. Для каждой фазы записывать только агрегированный безопасный снимок:

   - central video found / in viewport;
   - direct hit для start и end endpoint по отдельности;
   - video below top point-stack hit;
   - top hit interactive / control inherited;
   - control focusable, role-button, modal-or-dialog ancestor;
   - control disabled / ARIA-disabled;
   - top hit fixed ancestor и покрытие viewport/video;
   - отличие visual viewport от layout viewport;
   - наличие post-action JSON **только в обычном Collector run**, не в
     diagnostic-only режиме;
   - фаза наблюдения и reason code без внешнего текста.
4. Отдельно дать безопасное evidence о контексте, но не о содержимом профиля:

   - Collector использует configured persistent profile mount;
   - browser launch завершён успешно;
   - Reels navigation достигла ожидаемой фазы;
   - private viewer и Collector нельзя объявлять одним UI context только по
     факту общего profile mount.

   Запрещено хешировать либо выводить путь профиля, cookie names/counts или
   browser storage keys ради этого сравнения.
5. Вернуть один redacted JSON result в существующий workspace. Он содержит
   только булевы поля, enum phase/reason и счётчики. Любая ошибка завершается
   fail-closed reason code; traceback и исходные данные не выводятся.

## Изменяемые области

- `apps/api/app/instagram/collector/runtime/browser_feed.py` — пассивный probe
  и его bounded lifecycle orchestration.
- `apps/api/app/instagram/collector/contracts.py` — тип безопасного результата.
- `apps/api/app/instagram/collector/runtime/operator.py` и отдельный script —
  explicit diagnostic-only command и redacted result.
- unit/Chromium/runtime tests для фаз, отсутствия input и redaction.
- `docs/STATUS.md`, `docs/RISKS.md`, эта задача; при изменении service boundary
  также `docs/ARCHITECTURE.md` и ADR.

## Проверки до VPS

1. Unit tests: каждая фаза, все boolean-поля, timeout/error path и redaction.
2. Chromium test: diagnostic command не вызывает CDP touch/wheel/keyboard,
   downloader или persistence pipeline.
3. Regression: обычный Collector сохраняет current direct-hit gate и JSON-gate.
4. Ruff, `git diff --check`, secret audit.

## VPS-приёмка диагностики

1. Выполнить один diagnostic-only run с persistent test profile.
2. Убедиться, что число source objects, videos и collection runs не изменилось.
3. Проверить итоговый redacted result: во всех фазах видны только разрешённые
   boolean/enum/count fields.
4. Если interceptor исчезает без input, зафиксировать фазу исчезновения и
   реализовать только минимальный bounded wait/readiness repair.
5. Если interceptor остаётся во всех фазах, не запускать новый download run;
   следующая задача должна исследовать различие browser launch/navigation state
   без раскрытия private Instagram data.

## Условия допуска к следующему live 3/3

Допускается ровно один новый bounded live-run `3/3` только когда diagnostic-only
result показывает direct hit обоих endpoint выбранного video в точке отправки
input. Успех того run требует двух подтверждённых переходов, stable new media
identity и нового post-action authenticated feed JSON с другим canonical Reel
для каждого перехода, а также ffprobe/decode и отсутствие временных артефактов
для всех трёх durable results. Acceptance на `50` остаётся отдельным этапом.

## Паспорт тестового VPS (на 2026-09-06)

| Поле | Значение |
| --- | --- |
| Назначение | Временный тестовый Stage 10, не production |
| Provider hostname | `associated-teal` |
| Системный hostname | `associated-teal.ptr.network` |
| Public IPv4 | `171.22.119.246` |
| ОС | Ubuntu 24.04 |
| Тариф | DEs-3: 4 vCPU, 8 GB RAM, 120 GB NVMe, сеть до 25 Gbit/s |
| SSH user | `offline-reels` |
| Репозиторий на VPS | `/srv/offline-reels` |
| Развёрнутый код | `786dbcb` (`feat: add collector modal lifecycle diagnostic`) |
| Git `main` | `786dbcb` |
| Compose | `/srv/offline-reels/deploy/docker-compose.stage10.yml` с `.env.stage10` |
| Публичный тестовый вход | `https://offline-reels-associated-teal.tail5b33a7.ts.net` |
| Постоянные сервисы | `web`, `api`, `postgres`, `redis`, `minio`, `normalizer`, `stage10-ingress` — healthy/running |
| Временный viewer | `login-gateway` и `login-browser` остановлены; запускаются только для одноразовой operator session |

### Безопасные команды оператора

Подключение выполняется SSH-ключом пользователя Windows; пароль не требуется:

```powershell
ssh -i ~/.ssh/id_ed25519 offline-reels@171.22.119.246
```

На сервере состояние Stage 10 можно посмотреть без вывода secrets:

```bash
cd /srv/offline-reels/deploy
IMAGE_TAG=b62cf06 docker compose --env-file .env.stage10 -f docker-compose.stage10.yml ps
```

Не выполнять `cat .env.stage10`, `docker inspect` с environment, вывод
одноразовой login URL в общий чат или передачу cookie/profile files. Их значения
не нужны для реализации и приёмки этой диагностики.

## Результат Stage-10 diagnostic-only run

Один запуск выполнил все пять фиксированных фаз и вернул только разрешённые
агрегаты. Chromium запустился, persistent profile был configured, переход к
Reels достигнут. После navigation central video был найден, но оба direct-hit
endpoint оставались false. Начиная с первого bounded wait, и также в фазах
`before_collector_input` и после второго wait, верхний hit оставался
interactive/inherited, focusable, `role=button` с modal/dialog ancestor; video
оставался ниже него в point stack. visual viewport не отличался от layout
viewport. Следовательно, interceptor не исчезает без input, а его безопасный
wait/readiness repair отсутствует. Ни 3/3 live, ни acceptance на 50 Reel не
допускаются; следующий этап — отдельное aggregate-only сравнение browser
launch/navigation contexts.

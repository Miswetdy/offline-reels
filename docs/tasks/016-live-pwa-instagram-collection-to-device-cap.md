# TASK-016: Живой сбор Instagram по команде PWA до лимита устройства

## Проблема

После ручной profile-check с сообщением «Instagram подключён» bounded Linux run
(2026-09-06) снова дал 1/3 source-коммит, 0 подтверждённых переходов и
`TRANSITION_FAILED`. Это сообщение подтвердило авторизацию профиля, но не
подтвердило просмотр или закрытие modal dialog. Тот же focusable role-button
под modal/dialog ancestor продолжает перехватывать endpoints, поэтому touch
не отправлен.

В этом run наблюдались stable media change и post-action feed JSON, но не
canonical confirmation. JSON-gate корректно оставил сценарий fail-closed.
Profile-check viewer автоматически завершает сессию при обнаружении connected,
поэтому он не подходит для ручного разрешения existing feed dialog. Нужен
отдельный operator-controlled private viewer для просмотра авторизованной
ленты без auto-complete profile-check; только после ручного разрешения dialog
допустим новый bounded 3/3. Лимиты, endpoint hit-test, JSON-gate и блокировка
50 не меняются.

Реализован отдельный one-time operator viewer: ссылка `/connect/{id}?inspect=1`
после обычной single-use activation ведёт только на `/remote/{id}/interactive`.
Он использует существующие signed cookie, origin checks и private gateway relay,
но не poll-ит readiness и не complete-ит profile-check автоматически. До
истечения TTL оператор может вручную посмотреть authenticated feed dialog. Этот
viewer не публикует VNC/CDP/control service и не даёт Collector права нажимать
dialog. После ручного действия сессию нужно закрыть, затем выполнить bounded
3/3 как единственное доказательство результата.

После completed inspect-session и удаления одноразовой ссылки следующий
bounded Linux run снова дал 1/3 source-коммит, 0 переходов и
`TRANSITION_FAILED`. Все признаки modal interceptor сохранились: focusable
inherited role-button под modal/dialog ancestor, selected video ниже top
point-stack hit и отсутствие direct endpoint hit; touch не отправлен. Stable
media change и canonical confirmation отсутствуют, post-action JSON есть.

Следовательно, ручное действие не изменило состояние, наблюдаемое Collector.
Нельзя отличить dialog, который появляется заново в новом browser context, от
действия, не связанного с ним. Новые live-download attempts приостанавливаются,
пока operator workflow не сможет визуально подтвердить состояние dialog именно
в persistent profile/context Collector. Endpoint hit-test, JSON-gate, лимиты,
3/3 и 50 не меняются.

Первая inspect-попытка показала чёрный viewer, а после обновления страницы —
`Reconnect is required`; dialog не был просмотрен. Private browser control и
noVNC asset на сервере отвечают HTTP 200, поэтому это проблема внешнего viewer
path, а не авторизации или процесса браузера. `/interactive` переведён на
same-origin noVNC Core с явным текстовым состоянием connected/disconnected. Он
сохраняет one-time signed gateway path, не poll-ит readiness, не complete-ит
сессию и не публикует VNC/CDP/control service. До нового Collector run оператор
должен сначала увидеть состояние connected в этом viewer и только затем вручную
проверить dialog.

Bounded Linux run `d5d3dc5` (2026-09-06) дал 1/3 source-коммит, 0 переходов
и `TRANSITION_FAILED`, но установил причину. Верхнее препятствие — focusable
`role=button`, найденный через interactive ancestor внутри modal/dialog
ancestor. Оно не disabled/ARIA-disabled, не native button, anchor, form,
slider, contenteditable и не имеет touch-action:none. Эта кнопка по-прежнему
перекрывает endpoints над selected video, поэтому touch не отправлен.

Это evidence активного modal dialog поверх ленты, а не допустимой автоматической
input-цели. Boolean-признаки намеренно не раскрывают назначение dialog; runtime
не должен нажимать или закрывать его автоматически. Следующий операционный шаг
— вручную просмотреть и разрешить/закрыть dialog в authenticated interactive
session, затем повторить bounded 3/3. Endpoint hit-test, JSON-gate, лимиты и
блокировка 50 не меняются.

Bounded Linux run `4d77c2d` (2026-09-06) повторил 1/3 source-коммит,
0 подтверждённых переходов и `TRANSITION_FAILED`. Selected video остаётся ниже
верхнего hit в point stack, поэтому touch не отправлен. Local blocker не имеет
связи ни с одним visible video: не содержит и не находится в видео, не имеет
bounded common ancestor и не является sibling. У hit и control-предка нет
признака direct body child, у hit нет semantic page-shell ancestor.

Тем самым исключены классификации «слой другой видимой карточки» и page shell,
которые покрывает текущий probe. Это неопознанная локальная интерактивная
поверхность; данные не делают её безопасной input-целью. Post-action JSON есть,
стабильной media-смены и canonical confirmation нет. Далее нужно исследовать
только безопасные фиксированные признаки semantic role/interaction state этой
поверхности вместо расширения координат swipe. Endpoint hit-test, JSON-gate,
лимиты, 3/3 и 50 не меняются.

В bounded Linux run `d44d4c2` (2026-09-06) по-прежнему 1/3 source-коммит,
0 переходов и `TRANSITION_FAILED`. Video присутствует ниже верхнего hit в
`elementsFromPoint()` stack, следовательно, выбранные endpoint-точки реально
перекрыты верхней поверхностью. Обе точки находятся внутри visual viewport,
а visual и layout viewport совпадают. Верхний hit не имеет fixed-предка и не
покрывает ни viewport, ни видимую область video.

Это исключает координатное/viewport-расхождение и глобальный fixed overlay.
Препятствие локально для проверяемой области. Сохраняется inherited control,
но ни hit, ни control не связаны с selected video по доступным bounded
структурным признакам. Touch корректно не отправлен; стабильной media-смены и
canonical confirmation нет, post-action JSON есть. Следующая диагностика
должна безопасно отличить отдельный слой feed-card от page shell прежде чем
менять target input. Нельзя направлять жест в найденный верхний элемент или
ослаблять endpoint/JSON gates. 3/3 и 50 остаются заблокированными.

Последний bounded Linux run `db8a67c` (2026-09-06) снова дал 1/3 source-коммит,
0 переходов и `TRANSITION_FAILED`. Probe нашёл selected video в viewport, но
ни одна endpoint-точка не попала в него, поэтому touch не отправлен. Внешний
control был обнаружен только через interactive-предка попадания
(`control_inherited=true`): сам control не содержит видео и не покрывает его
видимую область. Попадание также не внутри и не содержит видео, не является
его sibling, не имеет зафиксированного близкого общего предка и не покрывает
видимую область. `pointer-events:none` и native controls — false.

Это исключает observed control как безопасную поверхность активной карточки.
Факты согласуются с внешней перехватывающей поверхностью, однако boolean
диагностика не идентифицирует её и не даёт права направлять в неё input.
Post-action JSON наблюдался без стабильной media-смены и canonical
confirmation. Далее требуются ограниченные безопасные структурные признаки,
различающие global overlay и несовпадение координат/viewport; затем —
evidence-backed ремонт. Endpoint hit-test, JSON-gate, лимиты, 3/3 и 50 остаются
без изменений.

Последний bounded Linux run `67d3833` (2026-09-06) дал 1/3 source-коммитов,
0 подтверждённых переходов и `TRANSITION_FAILED`. Probe успешно выполнен,
выбранное видео найдено в viewport. Среди проверенных точек наблюдались
`hit_test_miss_control=true` и `hit_test_miss_other_element=true`; обе категории
start/end-video-observed остались false. У выбранного видео
pointer-events:none=false и native-controls=false. Touch не отправлен,
стабильной media-смены и канонического подтверждения нет, post-action JSON есть.

Это подтверждает препятствия в проверенных точках, но не устанавливает их
конкретное назначение. Категория control включает попадание с управляющим
предком через closest(); остальные категории проверяются после неё. Следующее
исследование должно безопасными структурными boolean-признаками установить
связь препятствия с активной карточкой и покрытие видео. Нельзя автоматически
считать control или other_element допустимой целью жеста, отключать их
pointer-events или обходить endpoint/JSON gate. Ремонт выбирается после этой
проверки; диагностический run не подтверждает готовность 3/3 или 50.

Актуальная Linux-проверка `2ebce26` (2026-09-06): один source-коммит из трёх,
ноль подтверждённых переходов, terminal `TRANSITION_FAILED`. Probe выполнен
успешно (`attempted/evaluated=true`, `failed=false`), central video найден
и находится в viewport, но `hit_testable=false`; `mobile_swipe_performed=false`.
Стабильной media-смены не было, post-action JSON наблюдался без канонического
подтверждения. Следующий шаг — установить безопасной агрегированной
диагностикой причину отказа hit-test выбранных пар точек. Текущие данные не
устанавливают, какой элемент перехватывает точки или почему это происходит.
Нельзя ослаблять проверку обеих точек или JSON-gate на основании этого run.

Поправка к историческим описаниям ниже: до `2ebce26` wheel перезаписывал
touch-диагностику. Поэтому прежние all-false флаги не доказывают отсутствие
touch, scroll owner или видимого видео; такие объяснения были гипотезами.
Новый run с сохранением диагностики подтверждает отказ hit-test только для
этого запуска. Приёмка 3/3 и допуск к 50 остаются неподтверждёнными.

На Ubuntu Stage 10 подтверждены вход тестового Instagram-аккаунта, отдельное
session-first скачивание, ffprobe-валидация, MinIO/PostgreSQL-коммит,
нормализация, локальное сохранение PWA, офлайн-воспроизведение и синхронизация
просмотров. Однако один живой запуск Collector не может продолжить ленту после
первого успешно зафиксированного Reel.

В каждом воспроизведении наблюдается одинаковая безопасная картина:

- первый Reel проходит `detect → pause → download → validation → publish →
  db_commit`;
- первый и единственный допустимый повтор перехода выполняются;
- на повторе подтверждён pointer-wheel из центра мобильного viewport;
- за ограниченное окно не появляется новый канонический кандидат из
  authenticated feed JSON;
- запуск завершается `TRANSITION_FAILED`, не подменяя результат и не
  ослабляя изоляцию Chromium.

Последняя Linux-проверка после `e45e098` уточнила дефект. Она увидела два
стабильных наблюдения другой central media identity, то есть DOM/media-слой
визуально сменил элемент. Но после input-action checkpoint не поступил новый
канонический кандидат из authenticated feed JSON. Новый JSON-gate поэтому
верно не засчитал DOM-смену как переход и остановил run с
`TRANSITION_FAILED`.

Это не дефект JSON-gate и не повод возвращать URL, DOM-кандидат или старый
feed JSON как доказательство. Неисправна реальная browser-input цепочка:
текущая комбинация scroll owner / keyboard / pointer-wheel не гарантирует
продвижение именно того Instagram feed, который выдаёт новый authenticated
JSON-ответ.

Первая live-проверка native-touch реализации показала следующий конкретный
недостаток: на реальной Reels-странице probe не нашёл scrollable DOM owner или
document scroll root, поэтому корректно отказался отправлять touch
(`active_feed_target_available=false`, `mobile_swipe_performed=false`).
Keyboard/wheel после этого дали media-смену и post-action JSON observation, но
не другой канонический Reel. Значит, следующий ремонт обязан отличать
отсутствие обычного DOM scroll owner от отсутствия безопасной input-цели:
React/gesture feed может принимать user gesture непосредственно на central
video при CSS-locked root.

Повторная bounded Linux-проверка после ownerless-исправления также завершилась
`TRANSITION_FAILED` после одного durable-коммита. В ней все три признака
`active_feed_target_available`, `active_feed_target_in_viewport` и
`active_feed_target_hit_testable` остались `false`, а
`mobile_swipe_performed` — `false`. Следовательно, реализация fallback ещё не
доказала существование input-цели в реальной странице: это не отказ JSON-gate
и не evidence отправленного touch. При этом fallback keyboard/wheel вновь
увидел стабильную media-смену и post-action JSON, но не другой канонический
кандидат, поэтому fail-closed результат корректен.

Следовательно, нельзя считать готовым сценарий «одна кнопка PWA → новые
Instagram Reel → заполнение лимита». Предыдущие готовые видео не должны
использоваться, чтобы скрыть этот дефект.

## Цель

Реализовать и принять на Stage 10 полный пользовательский сценарий:

1. Пользователь открывает уже сопряжённую PWA и нажимает `Загрузить Reels`.
2. Именно это действие создаёт новую ручную команду сбора; оно не использует
   заранее подготовленный серверный каталог.
3. Изолированный Collector автоматически и последовательно исполняет эту
   команду в ранее авторизованном серверном профиле Instagram.
4. Новые Reel скачиваются session-first, валидируются, нормализуются и
   публикуются через существующий PostgreSQL/MinIO pipeline.
5. PWA последовательно сохраняет готовые MP4 в Cache Storage/IndexedDB до
   тестового локального лимита **50** роликов.
6. После отключения сети PWA открывается с домашнего экрана, а все сохранённые
   позиции доступны для офлайн-воспроизведения.

Production-значение лимита `500` не меняется. Значение `50` допускается только
как явно заданная Stage-10 build-time конфигурация.

## Этап 1 — исправление живого перехода

### Требования

- Перенести фактически подтверждённую механику transition из spike в runtime
  без изменения границы `FeedPort` и без чтения URL как доказательства
  перехода.
- Активный Reel определяется только по видимому центральному media-элементу;
  идентичность остаётся только в памяти процесса.
- Сохранить каскад: реальный scroll owner → `ArrowDown` → `PageDown` →
  pointer-wheel на 90% viewport из центра viewport.
- Действие считается успешным только после двух стабильных наблюдений другой
  active-media identity и последующего подтверждения другого канонического
  Reel из authenticated feed JSON.
- Если DOM-видео меняется, но канонический Reel не подтверждён, диагностировать
  это агрегированно и не считать переход успешным.
- Исследовать и исправить причину, по которой текущий input может сменить
  центральный media-элемент без нового feed JSON. До применения действия
  runtime должен безопасно проверить, что input направлен на реальный активный
  scroll owner/viewport Instagram, а не на preloaded/overlay DOM-элемент;
  после действия он должен дождаться нового authenticated JSON-наблюдения в
  пределах уже заданного deadline.
- Исправить native-touch target discovery: отсутствие scrollable DOM ancestor
  само по себе не является отказом, если central video имеет валидную видимую
  область и hit-test в выбранной точке возвращает этот video. В таком случае
  ограниченный touch-swipe направляется на hit-testable central video как
  реальный mobile gesture; owner/root используется для выбора геометрии, когда
  он существует. Нельзя отправлять жест в overlay/control или использовать
  синтетический DOM `scrollBy` как замену user input.
- Если текущий scroll owner не инициирует feed request, добавить только
  ограниченный эквивалент реального мобильного пользовательского действия,
  который создаёт это продвижение. Новый input обязан иметь unit/synthetic
  proof, process-local подтверждение и тот же timeout; он не может быть
  JavaScript-обходом React-состояния, прямым API-вызовом Instagram или
  неограниченным retry-loop.
- Расширить только aggregate diagnostics: отдельно показать факт стабильной
  media-смены и факт/отсутствие post-action JSON observation. Не сохранять
  коды, URL, response body, DOM-текст, координаты или идентичность media.
- Сохранить текущие пределы: один run — не более трёх Reel, два перехода,
  один retry, конечные timeout/byte/deadline. Не повышать эти границы для
  отладки.

### Приёмка этапа 1

- Новый ручной Linux run получает **3/3** новых Reel в одном запуске.
- Есть ровно два подтверждённых перехода; последний Reel не вызывает scroll.
- Для каждого подтверждённого перехода есть оба независимых признака:
  стабильная новая central media identity и хотя бы один новый
  post-action authenticated feed-JSON observation, из которого получен другой
  канонический Reel. Смена только первого признака остаётся terminal
  `TRANSITION_FAILED`.
- В live 3/3 хотя бы один переход имеет `mobile_swipe_performed=true` вместе
  с валидным available/in-viewport/hit-testable target; отсутствие обычного
  scroll owner не должно само по себе отключать native gesture на central
  video.
- Добавить безопасно агрегированную диагностику различения «probe не был
  вычислен» и «на странице нет видимого central video»; без DOM-текста,
  координат, URL, кодов или response body. Селекция input-цели должна быть
  согласована с селекцией active-media identity, чтобы наличие последней не
  могло молча сочетаться с `active_feed_target_available=false`.
- Все три source-коммита, нормализации и final MP4 проходят ffprobe/decode.
- Нет неочищенных временных файлов, staging-объектов, незавершённых jobs или
  невалидных DB-состояний.
- При сбое/отмене сохраняются только уже durable-коммиты; queued/running run
  получает корректный terminal status.

## Этап 2 — запуск от PWA и лимит 50

### Требования

- Добавить отдельный opt-in Collector command worker. Он опрашивает только
  `queued` manual runs одного явно заданного account ID и атомарно claim-ит
  конкретный run до запуска Chromium.
- Worker не импортируется в FastAPI, не получает HTTP-порт, Docker socket,
  host network или доступ к профилю login-gateway. Он использует тот же
  UID/GID 10001, read-only rootfs, AppArmor, seccomp, no-new-privileges,
  профильную блокировку и private egress, что текущий Collector.
- PWA для этой команды всегда создаёт новый manual run. Она не подменяет его
  историческим ready-каталогом. Готовые ранее Reel можно скачивать только
  после завершения именно созданной run-команды и только если они принадлежат
  её account/run history.
- После каждого завершённого малого bounded batch PWA ожидает нормализацию,
  последовательно сохраняет новые ready-файлы и создаёт следующий batch только
  пока локальный счётчик меньше 50. Одна активная команда на аккаунт; отмена
  прекращает следующий batch и не удаляет уже сохранённые файлы.
- Локальный лимит оформляется как валидируемый build-time параметр Stage 10
  (`1..500`); production default остаётся `500`, Stage 10 использует `50`.
- До старта Stage-10 acceptance готовый account catalog и локальная библиотека
  очищаются только отдельной подтверждённой процедурой с точной проверкой
  целевых записей/objects. Нельзя переиспользовать прежние acceptance Reel.

### Наблюдаемость

- В UI: только безопасные стадии `Получаем Reels`, `Подготавливаем видео`,
  `Загружаем на устройство`, счётчик и безопасное сообщение об остановке.
- В операторском результате: счётчики, event names, безопасные reason codes,
  bounded transition diagnostics и hashes агрегатов.
- Нельзя писать в UI, логи или result-файлы пароли, cookies, токены, raw
  media URL, Instagram username, DOM-текст, Reel ID/shortcode либо содержимое
  профиля.

### Приёмка этапа 2

1. До нажатия PWA на устройстве и в account-ready catalog нет тестовых
   позиций, которые могут быть зачтены как новый результат.
2. Нажатие `Загрузить Reels` создаёт единственный новый queued manual run;
   worker начинает его без ручного запуска команды оператором.
3. Собраны, нормализованы, опубликованы и локально сохранены ровно **50 новых
   Reel**. Каждый имеет source/run provenance текущей команды; дубликаты не
   расходуют лимит.
4. Очередь сохраняет файлы последовательно, переживает перезагрузку PWA и не
   использует background execution закрытого iOS-приложения.
5. После авиарежима, закрытия PWA и запуска с иконки доступны все 50 локальных
   позиций. Проверяются воспроизведение первой, средней и последней позиции, а
   также доступность остальных карточек без сети.
6. После возврата сети подтверждённые ручные свайпы синхронизируются
   account-scoped, не удаляют серверный canonical MP4 и исключают просмотренные
   Reel из последующих account catalogs.
7. Проверки не обнаруживают секретов, временных файлов, лишних published ports,
   ослабленного seccomp/AppArmor или `--no-sandbox`.

## Не входит в задачу

- автоматизация ввода пароля, 2FA, CAPTCHA или обход Instagram-защит;
- root Chromium, `--no-sandbox`, privileged-контейнер, `SYS_ADMIN`, host
  network, публикация VNC/CDP/X11 или экспорт профиля/cookies;
- фоновая загрузка в закрытой iOS PWA;
- изменение production-лимита 500 либо неограниченный сбор;
- использование старых acceptance-файлов как результатов нового запуска.

## Риски и стоп-условия

Instagram может выдать checkpoint, rate limit или изменить DOM. При любом
таком safe reason code worker останавливает текущий batch, сохраняет durable
результаты и не создаёт следующий. Продолжение требует нового явного действия
пользователя после устранения причины; retry-loop, параллельные Chromium
профили и увеличение лимитов для обхода стопа запрещены.

## Затрагиваемые области

- `apps/api/app/instagram/collector/runtime/browser_feed.py` и его unit tests;
- отдельный скрипт/worker очереди Collector и тесты persistence/claim/cancel;
- `deploy/docker-compose.stage10.yml` и Stage-10 runbook/проверки;
- `apps/web/components/library-dashboard.tsx`, offline queue и web tests;
- `docs/STATUS.md`, `docs/ARCHITECTURE.md`, `docs/RISKS.md`.

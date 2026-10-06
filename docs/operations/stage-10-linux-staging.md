# Stage 10: Linux staging

Ubuntu 24.04 amd64; preflight проверяет Docker Engine 29.7.2 и Compose 5.5.0.
Команды выполняются из корня reviewed checkout на Linux. Это runbook;
текущие результаты приёмки находятся в [STATUS](../STATUS.md).

Новый host проходит sandbox smoke до application deployment.
Live Instagram требует разрешённого тестового аккаунта, рабочего login
и отдельного bounded запуска. Старый Windows profile не переносить.

## 1. Checkout и sandbox

```sh
git status --short --branch
git rev-parse HEAD
git diff --check
sudo install -o root -g root -m 0644 deploy/security/offline-reels-collector.apparmor /etc/apparmor.d/offline-reels-collector
sudo apparmor_parser --skip-cache -r -W /etc/apparmor.d/offline-reels-collector
sudo -v
sh scripts/stage10-linux-preflight.sh
sh scripts/run-stage10-sandbox-smoke.sh
```

Smoke не имеет сети, secrets или persistent volumes. Требуются verified=true,
UID 10001, enforcing AppArmor, outer capabilities=0, NoNewPrivs=1,
Docker seccomp и nested Chromium child с дополнительным seccomp-BPF и нулевыми
capabilities. Не должно быть --no-sandbox или HTTP(S) requests.
Проверить kernel denials; при ошибке остановиться, не ослаблять sandbox.
Host-wide userns restriction сохраняется. Детали — [security README](../../deploy/security/README.md).

## 2. Environment и application services

Создать ignored `deploy/.env.stage10` из
[шаблона](../../deploy/.env.stage10.example), chmod 600.
Заменить все placeholders независимыми staging secrets, задать IMAGE_TAG,
account UUID и один HTTPS origin для NEXT_PUBLIC_API_BASE_URL,
FRONTEND_ORIGIN, MANAGEMENT_ORIGIN, без /api suffix.
При изменении public API URL пересобрать web.

```sh
dc() { docker compose --env-file deploy/.env.stage10 -f deploy/docker-compose.stage10.yml "$@"; }
sudo -v
sh scripts/stage10-linux-preflight.sh deploy/.env.stage10
dc config --quiet
dc build api web stage10-ingress
dc run --rm --no-deps stage10-ingress caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
dc up -d postgres redis minio
dc ps
```

После healthy data services:

```sh
dc run --rm minio-bootstrap
dc run --rm migrate
dc up -d --no-deps api web
dc up -d --no-deps stage10-ingress
curl --fail http://127.0.0.1:13080/health/ready
curl --fail http://127.0.0.1:13080/health/minio
curl --fail http://127.0.0.1:13080/videos
curl --include http://127.0.0.1:13080/api/management/session
sudo ss -lntp
```

/videos должен вернуть JSON, management/session без авторизации — 401.
Только ingress публикует 127.0.0.1:13080; web/API/data/browser ports закрыты.
На существующем видео проверить Range 206, Content-Range и Accept-Ranges:

```sh
curl --fail --range 0-1023 -D - -o /dev/null http://127.0.0.1:13080/videos/VIDEO_ID/stream
```

## 3. HTTPS

Сначала tailnet-only доступ и проверка маршрутов с другого устройства:

```sh
tailscale serve --bg http://127.0.0.1:13080
tailscale serve status
```

Проверить /, /offline, /videos, /health/ready, management 401,
CORS с точным configured origin и Range. В installed PWA принять ожидающее
обновление worker: старый shell мог содержать frontend /videos.

Funnel публичен. Только при разрешённой публичной приёмке переключить
взаимоисключающий HTTPS listener:

```sh
tailscale serve --https=443 off
tailscale funnel --https=443 --bg http://127.0.0.1:13080
tailscale funnel status
```

После временной публичной проверки: `tailscale funnel --https=443 off`.

## 4. Login

Collector не должен держать профиль. Не reset и не удалять профиль
для обычной повторной авторизации.

```sh
dc --profile instagram-login build login-browser
dc --profile instagram-login up -d --no-deps login-browser login-gateway
sh scripts/stage10-login-preflight.sh deploy/.env.stage10
```

После STAGE10_LOGIN_PREFLIGHT_OK paired устройство может нажать
«Подключить Instagram». Пароль/2FA/CAPTCHA и account confirmations вводит
пользователь в remote Chromium. Login считается готовым только на Reels boundary.
Проверка должна навигировать один раз, не скрывать ручное подтверждение бесконечно.

Перед Collector проверить graceful exit login-browser и освобождение lock.
Login и Collector используют один pinned Chrome for Testing; несовместимый
профиль нельзя force-open/downgrade. Guarded account reset — отдельная операция,
требующая явного разрешения на удаление profile.

## 5. Текущая приёмка Collector

Сначала no-download source-only diagnostic на подключённом test profile:

```sh
dc --profile collector build collector
dc --profile collector run --rm --no-deps collector identity-diagnostic --source-only
```

Exit 0 недостаточно: `source_only_candidate_count` должен быть 2.
Проверить safe aggregate result; raw IDs/URLs/response bodies не сохранять.
При ошибке не запускать повторяющийся сбор и не увеличивать limits.

После успешной диагностики и подтверждения bounded live-запуска:

```sh
dc --profile collector run --rm --no-deps collector
```

Compose задаёт target=3. Успех требует трёх новых durable sources, двух
source advances, валидных объектов и post-run verification; исходники могут
нуждаться в нормализации. AUTHENTICATED_FEED_EXHAUSTED — не успех.

Если требуется ручное вмешательство в UI Collector, использовать opt-in
collector-handoff с private gateway /handoff/* и подтверждением в том же
процессе. До confirm нет download/persistence; expiry/cancel прекращают run.
Одноразовый grant не копировать в логи/документацию.

## 6. Normalizer и iPhone

Отдельный `normalizer` profile запускает browser-free worker.
Для ограниченного прогона переопределите daemon command:

```sh
dc --profile normalizer build normalizer
dc --profile normalizer run --rm --no-deps normalizer uv run --no-sync python -m app.scripts.run_instagram_normalizer_worker --limit 3
dc --profile normalizer run --rm --no-deps normalizer uv run --no-sync python -m app.scripts.run_instagram_normalizer_worker --verify
```

Проверить ready catalog, H.264/yuv420p/AAC при наличии audio, decode и Range.
Затем [iPhone checklist](../acceptance/iphone.md).
Target 50/fresh PWA collection ещё требует отдельной реализации и приёмки;
текущий Stage 10 target=3 менять только после принятого 3/3.

## Остановка и rollback

Не выполнять down -v на staging: PostgreSQL/MinIO/profile volumes сохраняются.
Остановить только нужные opt-in сервисы. Не снимать AppArmor policy, пока
browser/Collector использует её. Возврат к reviewed image revision требует
отдельной оценки совместимости схемы; автоматического DB rollback нет.
Secrets, profiles, screenshots аккаунта и support dumps в checkout запрещены.

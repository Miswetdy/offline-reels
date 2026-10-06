# Развёртывание

Текущий live Collector проверяется на Ubuntu Stage 10:
[операционный runbook](../docs/operations/stage-10-linux-staging.md).
Готовность отдельных компонентов — в [STATUS](../docs/STATUS.md).

## Конфигурации

| Файл | Назначение |
| --- | --- |
| [compose.yaml](../compose.yaml) | Локальная разработка, опубликованные служебные порты |
| [docker-compose.stage10.yml](docker-compose.stage10.yml) | Linux staging, single origin, hardened browser |
| [docker-compose.prod.yml](docker-compose.prod.yml) | Базовая двухдоменная web/API/data топология |
| `docker-compose.stage*-fixture.yml` | Одноразовые synthetic проверки; не production данные |
| `docker-compose.*smoke.yml` | Изолированные проверки отдельных компонентов |

Старые Windows/Funnel конфигурации остаются в репозитории для соответствующих
fixtures. Они не являются текущей инструкцией Linux Instagram deployment.
Stage 4 Windows seccomp exception нельзя переносить на VPS.

## Базовая production-like топология

Это web/API/data foundation; полный login/Collector flow использует Stage 10.
Нужны APP_DOMAIN/API_DOMAIN с DNS на сервер, Docker Compose, reviewed revision,
SSH и входящие 80/443 для Caddy. Служебные сервисы доступны только внутри Docker.

Создайте ignored `deploy/.env.production` из
[шаблона](.env.production.example), права 0600; замените все placeholders.
Используйте независимые secrets, отдельные MinIO root/application credentials,
IMAGE_TAG выбранной ревизии.
NEXT_PUBLIC_API_BASE_URL=https://API_DOMAIN задаётся при build;
FRONTEND_ORIGIN=https://APP_DOMAIN без завершающего slash.

Из корня репозитория на Linux:

```sh
dc() { docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml "$@"; }
dc config --quiet
dc build
dc up -d postgres redis minio
dc ps
```

Дождитесь healthy; затем:

```sh
dc run --rm minio-bootstrap
dc run --rm migrate
dc up -d --no-deps api web
dc up -d --no-deps caddy
```

Проверить /health/live, /health/ready, /health/minio, /videos на API origin,
страницы / и /offline на app origin, точный CORS allowlist и stream Range 206/416.
API startup не выполняет миграции; migrate запускается перед rollout.
Runtime использует `uv run --no-sync`.

## Сохранность данных

Не коммитьте environment/profile files и не выводите resolved secrets в отчёт.
Не используйте `down -v` или `make migration-check` на retained данных.
Перед миграцией нужен backup; автоматизированный production backup/restore
и monitoring пока не завершены. Откат приложения не означает безопасный
downgrade схемы. Очистка fixture касается только его project/state path.

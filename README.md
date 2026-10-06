# Offline Reels

Персональная PWA для подготовки ленты Instagram Reels и просмотра без интернета.
Сервер собирает и нормализует видео; телефон скачивает их через Backend API
и воспроизводит локально.

**Сейчас:** офлайн-приложение и серверный конвейер реализованы. Stage 10 / TASK-018:
проверка стабильного сбора на Linux. Успешный текущий live-run 3/3 и полный
сценарий с 50 новыми роликами на iPhone ещё не подтверждены.

## Документация

- [Текущее состояние и блокер](docs/STATUS.md)
- [Границы MVP](docs/PRODUCT.md)
- [Архитектура](docs/ARCHITECTURE.md), [стек](docs/TECH_STACK.md)
- [Действующие решения](docs/TECH_DECISIONS.md), [риски](docs/RISKS.md)
- [Активная задача](docs/tasks/018-collector-operator-handoff-to-working-live-run.md)
- [Развёртывание](deploy/README.md), [Linux staging](docs/operations/stage-10-linux-staging.md)
- [Приёмка на iPhone](docs/acceptance/iphone.md)

Документы описывают актуальные контракты и незавершённую работу.
История экспериментов и закрытых задач хранится в Git.

## Локальный запуск

Нужны Docker Compose; для проверок на хосте — Node/npm и Python/uv
из [описания стека](docs/TECH_STACK.md). Команды выполняются из корня проекта.

```powershell
Copy-Item .env.example .env
docker compose up --build --detach
docker compose ps
```

Откройте `http://localhost:3000`. Локальная Compose-конфигурация публикует
служебные порты и не предназначена для VPS. Вход и сбор Instagram запускаются
отдельно; обычный запуск API не запускает браузер или workers.

Для тестового каталога используйте собственный разрешённый MP4:

```powershell
make seed-video FILE="C:\path\to\video.mp4"
make seed-videos DIR="C:\path\to\videos"
```

Seed проверяет и нормализует файл, затем сохраняет его в MinIO и PostgreSQL.
Не коммитьте media, реальные `.env`, профили, cookies или токены.

## Проверки

```powershell
make check
git diff --check
```

`make check` запускает frontend tests/lint/typecheck/build, Ruff, API unit tests
и отдельную Docker-инфраструктуру integration tests. Требует GNU Make,
PowerShell, Docker, npm и uv. Отдельно доступны `make web-check`,
`make api-unit-check`, `make api-integration-check`.

`make migration-check` делает downgrade до base: используйте только
одноразовую базу, не staging/production.

## Основные маршруты

| Маршрут | Назначение |
| --- | --- |
| `/` | Панель подключения и ручной загрузки |
| `/offline` | Локальная вертикальная лента |
| `GET /videos` | Каталог с подписанным курсором |
| `GET /videos/{id}/stream` | MP4 через API, single Range |
| `/api/management/*` | Защищённое управление устройством и Instagram |
| `/health/live`, `/health/ready` | API; готовность PostgreSQL и Redis |
| `/health/minio` | Отдельная диагностика хранилища |

Для iPhone используйте HTTPS и скачивайте видео внутри установленной
Home Screen PWA: её хранилище отделено от Safari.

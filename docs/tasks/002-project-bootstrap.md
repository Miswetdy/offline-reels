# TASK-002: Production project bootstrap

## Цель

Создать воспроизводимый production-каркас Offline Reels для дальнейшей разработки.

## Нужно реализовать

- frontend-каркас;
- backend-каркас;
- Docker Compose;
- PostgreSQL;
- Redis;
- MinIO;
- health-check backend;
- простую стартовую страницу frontend;
- общие команды запуска и проверки;
- инструкции в README.

## Предполагаемая структура

offlineReels/
├── apps/
│   ├── web/
│   └── api/
├── services/
│   ├── instagram-collector/
│   └── media-worker/
├── docs/
├── spikes/
├── compose.yaml
├── Makefile
└── .env.example

## Вне задачи

- Instagram-интеграция;
- загрузка видео;
- пользовательская авторизация;
- бизнес-логика ленты;
- Celery-задачи;
- production deployment.

## Критерии готовности

1. Все сервисы запускаются одной документированной командой.
2. Backend health-check возвращает успешный ответ.
3. Frontend открывается и показывает статус Backend.
4. PostgreSQL, Redis и MinIO доступны локально.
5. Секреты не хранятся в Git.
6. Есть `.env.example`.
7. Тесты и проверки проходят.
8. Документация обновлена.
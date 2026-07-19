# TASK-003: First video vertical slice

## Цель

Реализовать первый end-to-end сценарий видео через PostgreSQL, MinIO, Backend API и Frontend.

## Пользовательский сценарий

1. Тестовый MP4 загружается seed-командой в MinIO.
2. Метаданные видео записываются в PostgreSQL.
3. Backend API возвращает список видео.
4. Frontend отображает карточку видео.
5. Видео воспроизводится через Backend API.
6. Перемотка работает через HTTP Range requests.

## Нужно реализовать

### PostgreSQL
- таблицу videos;
- Alembic-миграцию;
- SQLAlchemy-модель;
- repository layer.

### MinIO
- клиент объектного хранилища;
- создание bucket при необходимости;
- загрузку тестового MP4;
- получение метаданных объекта;
- чтение диапазона байтов.

### Backend API
- GET /videos;
- GET /videos/{video_id};
- GET /videos/{video_id}/stream;
- корректную поддержку HTTP Range;
- Content-Type, Content-Length, Content-Range и Accept-Ranges;
- обработку отсутствующих записей и объектов.

### Seed
- идемпотентную команду загрузки одного тестового MP4;
- повторный запуск не должен создавать дубликаты;
- путь к файлу передаётся явно;
- реальные видео не хранятся в Git.

### Frontend
- страницу /videos;
- получение списка через Backend API;
- карточку ролика;
- HTML5 video player;
- состояния loading, empty и error.

### Тесты
- миграция;
- repository/service;
- API списка и детализации;
- полный и частичный streaming;
- некорректный Range;
- отсутствующий ролик;
- frontend loading/success/error/empty;
- production builds.

## Вне задачи

- Instagram;
- Playwright Collector;
- Celery;
- автоматическое скачивание;
- пользовательская загрузка;
- авторизация;
- offline caching;
- service worker;
- свайпы;
- infinite scroll;
- рекомендации;
- лайки и комментарии.

## Критерии готовности

1. Seed создаёт один тестовый ролик.
2. Повторный seed не создаёт дубликат.
3. Файл существует в MinIO.
4. Метаданные существуют в PostgreSQL.
5. GET /videos возвращает ролик.
6. Страница /videos отображает ролик.
7. Видео воспроизводится.
8. Перемотка работает.
9. После перезапуска Compose ролик остаётся доступен.
10. Отсутствующий объект обрабатывается без падения API.
11. Тесты, lint, typecheck и production builds проходят.
12. Документация обновлена.
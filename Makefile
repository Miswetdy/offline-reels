COMPOSE := docker compose
WEB_DIR := apps/web
API_DIR := apps/api

.PHONY: up down logs ps config check web-check api-check web-install api-install migration-check minio-health

up:
	$(COMPOSE) up --build --detach

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs --follow

ps:
	$(COMPOSE) ps

config:
	$(COMPOSE) config

web-install:
	npm --prefix $(WEB_DIR) ci

api-install:
	uv --directory $(API_DIR) sync --all-groups --frozen

web-check: web-install
	npm --prefix $(WEB_DIR) run test
	npm --prefix $(WEB_DIR) run lint
	npm --prefix $(WEB_DIR) run typecheck
	npm --prefix $(WEB_DIR) run build

api-check: api-install
	uv --directory $(API_DIR) run ruff check .
	uv --directory $(API_DIR) run pytest

check: web-check api-check

migration-check:
	$(COMPOSE) exec --no-TTY api uv run alembic downgrade base
	$(COMPOSE) exec --no-TTY api uv run alembic upgrade head

minio-health:
	$(COMPOSE) exec --no-TTY api uv run python -c "from urllib.request import urlopen; print(urlopen('http://minio:9000/minio/health/live', timeout=5).read().decode())"

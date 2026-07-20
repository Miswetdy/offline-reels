COMPOSE := docker compose
TEST_COMPOSE := docker compose --project-name offline-reels-task003-tests --profile test
WEB_DIR := apps/web
API_DIR := apps/api

.PHONY: up down logs ps config check web-check api-check api-unit-check api-integration-check web-install api-install migration-check minio-health seed-video seed-videos

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

api-unit-check: api-install
	uv --directory $(API_DIR) run ruff check .
	uv --directory $(API_DIR) run pytest tests/unit tests/test_health.py

api-integration-check:
	powershell -NoProfile -Command "$$ErrorActionPreference = 'Continue'; $(TEST_COMPOSE) up --build --abort-on-container-exit --exit-code-from api-tests api-tests; $$testExit = $$LASTEXITCODE; $(TEST_COMPOSE) down --volumes --remove-orphans; exit $$testExit"

api-check: api-unit-check api-integration-check

check: web-check api-check

migration-check:
	$(COMPOSE) exec --no-TTY api uv run alembic downgrade base
	$(COMPOSE) exec --no-TTY api uv run alembic upgrade head

minio-health:
	$(COMPOSE) exec --no-TTY api uv run python -c "from urllib.request import urlopen; print(urlopen('http://minio:9000/minio/health/live', timeout=5).read().decode())"

seed-video:
	powershell -NoProfile -Command "$$file = '$(FILE)'; if ([string]::IsNullOrWhiteSpace($$file) -or -not (Test-Path -LiteralPath $$file -PathType Leaf)) { Write-Error 'FILE must be an existing local file.'; exit 2 }; $(COMPOSE) up --detach api minio; if ($$LASTEXITCODE -ne 0) { exit $$LASTEXITCODE }; $(COMPOSE) cp $$file api:/tmp/task-003-seed.mp4; if ($$LASTEXITCODE -ne 0) { exit $$LASTEXITCODE }; $(COMPOSE) exec --no-TTY api uv run python -m app.scripts.seed_video --file /tmp/task-003-seed.mp4; $$seedExit = $$LASTEXITCODE; $(COMPOSE) exec --no-TTY api rm -f /tmp/task-003-seed.mp4; exit $$seedExit"

seed-videos:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/seed-videos.ps1 -Directory "$(DIR)"

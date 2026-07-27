FROM python:3.14.3-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_CACHE=1

RUN apt-get update \
    && apt-get install --no-install-recommends --yes ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.11.29

WORKDIR /app

FROM base AS production
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 8000
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000"]

FROM base AS test
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --all-groups
COPY . .
CMD ["sh", "-c", "uv run alembic upgrade head && uv run pytest tests/integration"]

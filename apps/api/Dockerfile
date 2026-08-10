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

# The normalizer is deliberately browser-free. It shares only the production
# dependency set with API, but has its own non-root runtime target.
FROM base AS normalizer
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev \
    && groupadd --gid 10002 normalizer \
    && useradd --uid 10002 --gid normalizer --create-home --home-dir /home/normalizer normalizer \
    && install --directory --owner normalizer --group normalizer --mode 0750 /normalizer/workspace
COPY --chown=normalizer:normalizer app ./app
COPY --chown=normalizer:normalizer alembic ./alembic
COPY --chown=normalizer:normalizer alembic.ini ./
USER normalizer
CMD ["uv", "run", "--no-sync", "python", "-m", "app.scripts.run_instagram_normalizer_worker"]

# This image is intentionally separate from the API target above.  It is the
# only image that installs the optional browser/downloader runtime.
FROM base AS collector
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN apt-get update \
    && apt-get install --no-install-recommends --yes tini \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra collector \
    && uv run --no-sync playwright install --with-deps chromium \
    && groupadd --gid 10001 collector \
    && useradd --uid 10001 --gid collector --create-home --home-dir /home/collector collector \
    && install --directory --owner collector --group collector --mode 0750 \
        /collector/profile /collector/workspace \
    && chown --recursive collector:collector /ms-playwright
COPY --chown=collector:collector app ./app
COPY --chown=collector:collector alembic ./alembic
COPY --chown=collector:collector alembic.ini ./
COPY --chown=collector:collector docker/collector-entrypoint.sh /usr/local/bin/collector-entrypoint
RUN chmod 0555 /usr/local/bin/collector-entrypoint
USER collector
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/collector-entrypoint"]
CMD ["help"]

FROM base AS test
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --all-groups
COPY . .
CMD ["sh", "-c", "uv run alembic upgrade head && uv run pytest tests/integration"]

FROM collector AS collector-test
USER root
RUN uv sync --frozen --all-groups --extra collector \
    && chown --recursive collector:collector /app/.venv
COPY --chown=collector:collector tests ./tests
USER collector

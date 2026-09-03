#!/bin/sh
# Explicit acceptance action: builds and runs only the networkless one-shot
# Collector sandbox service. It does not start the staging application stack.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$REPOSITORY_ROOT"

sh scripts/stage10-linux-preflight.sh

compose() {
  docker compose -f deploy/docker-compose.stage10-sandbox-smoke.yml "$@"
}

compose build collector-sandbox-smoke
smoke_output=$(compose run --rm --no-deps collector-sandbox-smoke)
printf '%s\n' "$smoke_output"
printf '%s\n' "$smoke_output" | grep -q '"verified": true' || {
  printf 'stage10-sandbox-smoke: FAIL\n' >&2
  exit 1
}
printf 'stage10-sandbox-smoke: PASS\n'

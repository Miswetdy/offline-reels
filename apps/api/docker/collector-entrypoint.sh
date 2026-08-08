#!/bin/sh
set -eu

case "${1:-help}" in
  fixture)
    shift
    exec uv run --no-sync python -m app.scripts.run_instagram_collector_container_fixture "$@"
    ;;
  help|--help|-h)
    echo "usage: collector-entrypoint fixture [fixture options]" >&2
    exit 0
    ;;
  *)
    echo "refusing to run an implicit or live Collector command" >&2
    exit 64
    ;;
esac

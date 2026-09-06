#!/bin/sh
set -eu

case "${1:-help}" in
  fixture)
    shift
    exec uv run --no-sync python -m app.scripts.run_instagram_collector_container_fixture "$@"
    ;;
  sandbox-smoke)
    shift
    exec uv run --no-sync python -m app.scripts.verify_chromium_sandbox "$@"
    ;;
  identity-diagnostic)
    shift
    exec xvfb-run --auto-servernum --server-args="-screen 0 430x800x24 -nolisten tcp" \
      uv run --no-sync python -m app.scripts.diagnose_instagram_reels_identity "$@"
    ;;
  modal-lifecycle-diagnostic)
    shift
    exec xvfb-run --auto-servernum --server-args="-screen 0 430x800x24 -nolisten tcp" \
      uv run --no-sync python -m app.scripts.diagnose_instagram_modal_lifecycle "$@"
    ;;
  live)
    shift
    # A private X server retains the existing headed Collector behavior. It
    # listens on no TCP socket and is never exposed outside the container.
    exec xvfb-run --auto-servernum --server-args="-screen 0 430x800x24 -nolisten tcp" \
      uv run --no-sync python -m app.scripts.run_instagram_collector_live "$@"
    ;;
  help|--help|-h)
    echo "usage: collector-entrypoint {fixture|sandbox-smoke|identity-diagnostic|modal-lifecycle-diagnostic|live} [options]" >&2
    exit 0
    ;;
  *)
    echo "refusing to run an implicit Collector command" >&2
    exit 64
    ;;
esac

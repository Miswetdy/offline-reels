"""Explicit command entrypoint; importing FastAPI never starts this worker."""

from __future__ import annotations

import argparse
import json
import signal
import sys
from threading import Event
from time import sleep

from app.core.settings import get_settings
from app.db.session import create_session_factory
from app.instagram.normalizer.worker import InstagramNormalizerWorker
from app.storage.minio import MinioVideoStorage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Instagram normalization queue worker.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Claim at most one job.")
    mode.add_argument("--daemon", action="store_true", help="Poll until SIGTERM/SIGINT.")
    mode.add_argument("--status", action="store_true", help="Read-only queue aggregates.")
    mode.add_argument("--verify", action="store_true", help="Read-only queue aggregates alias.")
    mode.add_argument(
        "--reconcile", action="store_true", help="Recover expired leases and source cleanup."
    )
    parser.add_argument("--limit", type=int, default=1, help="Maximum jobs in non-daemon mode.")
    parser.add_argument("--poll-seconds", type=float, default=5.0, help="Daemon poll delay.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit < 1 or args.poll_seconds <= 0:
        return 2
    if args.once:
        args.limit = 1
    cancellation = Event()
    signal.signal(signal.SIGTERM, lambda *_: cancellation.set())
    signal.signal(signal.SIGINT, lambda *_: cancellation.set())
    settings = get_settings()
    storage = MinioVideoStorage(settings)
    worker = InstagramNormalizerWorker(
        create_session_factory(settings),
        storage,
        cancellation=cancellation,
        progress=_safe_progress,
    )
    try:
        if args.status:
            print(json.dumps(worker.status().__dict__, sort_keys=True))
            return 0
        if args.verify:
            print(json.dumps(worker.verify(), sort_keys=True))
            return 0
        if args.reconcile:
            print(json.dumps(worker.reconcile(), sort_keys=True))
            return 0
        if args.daemon:
            worker.reconcile()
            while not cancellation.is_set():
                if not worker.run_once():
                    sleep(args.poll_seconds)
            return 0
        worker.reconcile()
        for _ in range(args.limit):
            if cancellation.is_set() or not worker.run_once():
                break
        return 0
    except Exception:
        print(json.dumps({"event": "failed", "reason_code": "MINIO_TRANSIENT_FAILURE"}))
        return 1


def _safe_progress(event: dict[str, object]) -> None:
    print(json.dumps(event, sort_keys=True), flush=True)


if __name__ == "__main__":
    sys.exit(main())

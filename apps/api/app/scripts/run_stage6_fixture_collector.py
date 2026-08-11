"""Disposable Stage 6 fixture controller; it never contacts Instagram."""

from __future__ import annotations

import argparse
import time
from datetime import UTC, datetime
from uuid import UUID

from app.core.settings import get_settings
from app.db.models.instagram import InstagramCollectionRun
from app.db.session import create_session_factory
from app.instagram.collector.persistence import CollectorPersistence
from app.instagram.contracts import CollectionRunStatus


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 6 disposable fixture Collector")
    parser.add_argument("--account-id", required=True, type=UUID)
    parser.add_argument("--delay-seconds", default=8, type=int, choices=range(1, 31))
    arguments = parser.parse_args(argv)
    sessions = create_session_factory(get_settings())
    claimed = CollectorPersistence(sessions).claim_queued_run(arguments.account_id)
    if claimed is None:
        return 2
    time.sleep(arguments.delay_seconds)
    with sessions.begin() as db:
        current = db.get(InstagramCollectionRun, claimed.id, with_for_update=True)
        if current is None:
            return 2
        if current.cancel_requested_at is not None:
            current.status = CollectionRunStatus.CANCELLED.value
            current.stop_reason_code = "CANCELLED_BY_USER"
        else:
            current.source_committed_count = current.target_count
            current.status = CollectionRunStatus.COMPLETED.value
            current.stop_reason_code = None
        current.completed_at = datetime.now(UTC)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Explicit recovery command: cancel only one specified active Collector run."""

import argparse
from uuid import UUID

from app.core.settings import Settings
from app.db.session import create_session_factory
from app.instagram.collector.contracts import CancelRunOutcome
from app.instagram.collector.persistence import CollectorPersistence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cancel one active Instagram Collector run")
    parser.add_argument("run_id", type=UUID)
    arguments = parser.parse_args(argv)
    try:
        outcome = CollectorPersistence(create_session_factory(Settings())).cancel_run(
            arguments.run_id, "CANCELLED_BY_USER"
        )
    except Exception:
        print('{"phase":"stage-3b-recovery","stop_reason_code":"DATABASE_WRITE_FAILED"}')
        return 1
    if outcome is CancelRunOutcome.CANCELLED:
        reason = "CANCELLED_BY_USER"
        exit_code = 0
    elif outcome is CancelRunOutcome.NOT_FOUND:
        reason = "RUN_NOT_FOUND"
        exit_code = 1
    else:
        reason = "RUN_ALREADY_TERMINAL"
        exit_code = 1
    print(f'{{"phase":"stage-3b-recovery","stop_reason_code":"{reason}"}}')
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

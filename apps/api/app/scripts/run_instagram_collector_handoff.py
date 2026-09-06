"""One-time operator handoff which retains the already-open Collector browser."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from uuid import UUID

from app.core.settings import Settings
from app.instagram.collector.runtime.browser_feed import PlaywrightReelsFeed
from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode
from app.instagram.collector.runtime.handoff_state import HANDOFF_TTL, HandoffStateStore
from app.instagram.collector.runtime.operator import (
    run_stage_3b,
    safe_summary_json,
    write_safe_result,
)
from app.instagram.collector.runtime.paths import collector_repository_root
from app.instagram.collector.runtime.settings import CollectorRuntimeSettings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One-time same-process Collector handoff")
    parser.add_argument("--account-id", type=UUID, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    args = parser.parse_args(argv)
    runtime, repository_root = (
        CollectorRuntimeSettings.from_environment(),
        collector_repository_root(Path(__file__)),
    )
    store = HandoffStateStore(args.state_root)
    feed = None
    try:
        runtime.require_live(repository_root=repository_root)
        # This opens/navigates/readies the persistent browser only.  No input,
        # downloader, database, Redis or object-store adapter exists yet.
        feed = PlaywrightReelsFeed.open(
            args.account_id, runtime, repository_root=repository_root, allow_login_bootstrap=True
        )
        feed.current()
        created = store.create(ttl=HANDOFF_TTL)
        # The launch secret is a 0600 private-volume file, never stdout/logs or
        # a result. The operator combines it with this non-secret session id.
        print(f'{{"phase":"handoff","session_id":"{created.session_id}"}}')
        state = "pending"
        while state in {"pending", "active"}:
            time.sleep(0.25)
            state = store.state(created.session_id)
        if state != "confirmed":
            code = (
                RuntimeReasonCode.HANDOFF_EXPIRED
                if state == "expired"
                else RuntimeReasonCode.HANDOFF_CANCELLED
            )
            print(f'{{"phase":"handoff","stop_reason_code":"{code.value}"}}')
            return 1
        summary, transcript, reason = run_stage_3b(
            runtime=runtime,
            app_settings=Settings(),
            repository_root=repository_root,
            confirm=lambda: True,
            wait_ready=lambda _: True,
            account_id=args.account_id,
            existing_feed=feed,
        )
        feed = None  # run_stage_3b owns and closes the retained browser.
        result = safe_summary_json(summary, transcript, reason)
        assert runtime.workspace_root is not None
        write_safe_result(runtime.workspace_root, result)
        print(result)
        return 0 if summary is not None and summary.status == "completed" else 1
    except CollectorRuntimeError as error:
        print(f'{{"phase":"handoff","stop_reason_code":"{error.code.value}"}}')
        return 1
    finally:
        if feed is not None:
            feed.close()


if __name__ == "__main__":
    raise SystemExit(main())

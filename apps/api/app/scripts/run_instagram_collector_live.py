"""Explicit Stage 3B manual operator command. It is never imported by FastAPI."""

import argparse
from pathlib import Path

from app.core.settings import Settings
from app.instagram.collector.runtime.errors import CollectorRuntimeError
from app.instagram.collector.runtime.operator import (
    STAGE_3B_TARGET,
    run_stage_3b,
    safe_summary_json,
    wait_for_operator_enter,
    write_safe_result,
)
from app.instagram.collector.runtime.paths import collector_repository_root
from app.instagram.collector.runtime.settings import CollectorRuntimeSettings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bounded manual Instagram Collector operator run")
    parser.add_argument("--target", type=int, default=STAGE_3B_TARGET)
    arguments = parser.parse_args(argv)
    if arguments.target != STAGE_3B_TARGET:
        print('{"phase":"stage-3b","stop_reason_code":"INVALID_TARGET"}')
        return 2
    print(
        "Open the test Instagram account manually, open personal Reels, "
        "centre one Reel, then press Enter."
    )
    runtime = CollectorRuntimeSettings.from_environment()
    app_settings = Settings()
    repository_root = collector_repository_root(Path(__file__))

    def confirm() -> bool:
        print("Collect exactly 3 Reels with session-first download? [y/N]")
        return input().strip() == "y"

    try:
        summary, transcript, reason = run_stage_3b(
            runtime=runtime,
            app_settings=app_settings,
            repository_root=repository_root,
            confirm=confirm,
            wait_ready=wait_for_operator_enter,
        )
    except CollectorRuntimeError as error:
        print(f'{{"phase":"stage-3b","stop_reason_code":"{error.code.value}"}}')
        return 1
    except Exception:
        print('{"phase":"stage-3b","stop_reason_code":"COLLECTOR_FAILED"}')
        return 1
    result = safe_summary_json(summary, transcript, reason)
    assert runtime.workspace_root is not None
    write_safe_result(runtime.workspace_root, result)
    print(result)
    verified = (
        transcript.verification is not None
        and transcript.verification.get("verified") is True
    )
    return 0 if summary is not None and summary.status == "completed" and verified else 1


if __name__ == "__main__":
    raise SystemExit(main())

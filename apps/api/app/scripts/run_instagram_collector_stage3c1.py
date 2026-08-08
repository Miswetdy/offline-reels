"""Manual Stage 3C.1 continuation command. Never imported by FastAPI."""

import argparse
from pathlib import Path

from app.core.settings import Settings
from app.instagram.collector.runtime.errors import CollectorRuntimeError
from app.instagram.collector.runtime.operator import wait_for_operator_enter
from app.instagram.collector.runtime.paths import collector_repository_root
from app.instagram.collector.runtime.settings import CollectorRuntimeSettings
from app.instagram.collector.runtime.stage3c1 import (
    STAGE_3C1_DESIRED_TOTAL,
    run_stage3c1,
    safe_stage3c1_json,
    write_stage3c1_result,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manual Stage 3C.1 Instagram Collector continuation"
    )
    parser.add_argument("--desired-total", type=int, default=STAGE_3C1_DESIRED_TOTAL)
    arguments = parser.parse_args(argv)
    if arguments.desired_total != STAGE_3C1_DESIRED_TOTAL:
        print('{"phase":"stage-3c1","stop_reason_code":"INVALID_TARGET"}')
        return 2
    print("Open personal Instagram Reels, centre one Reel, then press Enter.")
    runtime = CollectorRuntimeSettings.from_environment()
    repository_root = collector_repository_root(Path(__file__))
    try:
        summary, transcript, plan, reason = run_stage3c1(
            runtime=runtime,
            app_settings=Settings(),
            repository_root=repository_root,
            desired_total=arguments.desired_total,
            confirm=lambda: input("Continue to exactly 10 durable Reels? [y/N] ").strip() == "y",
            wait_ready=wait_for_operator_enter,
        )
    except CollectorRuntimeError as error:
        print(f'{{"phase":"stage-3c1","stop_reason_code":"{error.code.value}"}}')
        return 1
    except Exception:
        print('{"phase":"stage-3c1","stop_reason_code":"COLLECTOR_FAILED"}')
        return 1
    result = safe_stage3c1_json(summary, transcript, plan, reason)
    assert runtime.workspace_root is not None
    write_stage3c1_result(runtime.workspace_root, result)
    print(result)
    verified = (
        transcript.verification is not None and transcript.verification.get("verified") is True
    )
    if plan.remaining == 0:
        return 0 if reason is None and verified else 1
    return (
        0
        if summary is not None and summary.status == "completed" and reason is None and verified
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())

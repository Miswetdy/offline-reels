"""Run the explicit, passive Collector modal lifecycle diagnostic."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from uuid import UUID

from app.instagram.collector.runtime.modal_lifecycle import (
    run_modal_lifecycle_diagnostic,
    safe_modal_lifecycle_json,
    write_modal_lifecycle_result,
)
from app.instagram.collector.runtime.paths import collector_repository_root
from app.instagram.collector.runtime.settings import CollectorRuntimeSettings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Passive aggregate-only Collector modal diagnostic"
    )
    parser.add_argument("--account-id", default=os.environ.get("COLLECTOR_ACCOUNT_ID"), type=UUID)
    arguments = parser.parse_args(argv)
    if arguments.account_id is None:
        print('{"reason_code":"COLLECTOR_DISABLED"}')
        return 2
    runtime = CollectorRuntimeSettings.from_environment()
    result = run_modal_lifecycle_diagnostic(
        account_id=arguments.account_id,
        runtime=runtime,
        repository_root=collector_repository_root(Path(__file__)),
    )
    payload = safe_modal_lifecycle_json(result)
    try:
        if runtime.workspace_root is None:
            raise OSError
        write_modal_lifecycle_result(runtime.workspace_root, payload)
    except OSError:
        print('{"reason_code":"RESULT_WRITE_FAILED"}')
        return 1
    print(payload)
    return 0 if result.reason_code is None else 1


if __name__ == "__main__":
    raise SystemExit(main())

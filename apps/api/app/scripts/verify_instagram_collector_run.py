"""Read-only verification using the immutable pre-run baseline in a result file."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from app.core.settings import Settings
from app.db.session import create_session_factory
from app.instagram.collector.runtime.minio_client import create_collector_minio_client
from app.instagram.collector.runtime.verification import CollectorPostRunVerifier, RunBaseline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Collector run verification")
    parser.add_argument("result_file", type=Path)
    arguments = parser.parse_args(argv)
    try:
        payload = json.loads(arguments.result_file.read_text(encoding="utf-8"))
        summary = payload.get("summary")
        run_id = UUID(summary["run_id"])
        baseline = RunBaseline.from_safe_dict(payload.get("baseline"))
        events = payload.get("events")
        if baseline is None or not isinstance(events, list):
            raise ValueError
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        print('{"phase":"stage-3b-verification","reason_code":"BASELINE_UNAVAILABLE","verified":false}')
        return 1

    settings = Settings()
    sessions = create_session_factory(settings)
    result = CollectorPostRunVerifier(
        sessions,
        create_collector_minio_client(settings),
        settings.minio_bucket,
    ).verify(
        run_id,
        baseline=baseline,
        transcript=events,
        workspace_root=arguments.result_file.resolve(strict=False).parents[1],
    )
    output = asdict(result)
    output["run_id"] = str(result.run_id)
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0 if result.verified else 1


if __name__ == "__main__":
    raise SystemExit(main())

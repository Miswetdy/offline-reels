"""One-shot aggregate-only Reel identity diagnostic for a connected test profile."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from uuid import UUID

from app.instagram.collector.runtime.browser_feed import PlaywrightReelsFeed
from app.instagram.collector.runtime.errors import CollectorRuntimeError
from app.instagram.collector.runtime.paths import collector_repository_root
from app.instagram.collector.runtime.settings import CollectorRuntimeSettings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate-only Instagram Reel identity diagnostic"
    )
    parser.add_argument("--account-id", default=os.environ["COLLECTOR_ACCOUNT_ID"], type=UUID)
    arguments = parser.parse_args(argv)
    runtime = CollectorRuntimeSettings.from_environment()
    feed: PlaywrightReelsFeed | None = None
    try:
        feed = PlaywrightReelsFeed.open(
            arguments.account_id,
            runtime,
            repository_root=collector_repository_root(Path(__file__)),
        )
        result = feed.identity_structure_diagnostics()
    except CollectorRuntimeError as error:
        print(json.dumps({"phase": "identity-diagnostic", "reason_code": error.code.value}))
        return 1
    finally:
        if feed is not None:
            feed.close()
    print(json.dumps({"phase": "identity-diagnostic", "result": result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

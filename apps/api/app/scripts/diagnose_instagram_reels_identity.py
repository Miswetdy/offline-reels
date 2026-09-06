"""One-shot aggregate-only Reel identity diagnostic for a connected test profile."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
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
    parser.add_argument("--transition", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    arguments = parser.parse_args(argv)
    runtime = CollectorRuntimeSettings.from_environment()
    feed: PlaywrightReelsFeed | None = None
    try:
        feed = PlaywrightReelsFeed.open(
            arguments.account_id,
            runtime,
            repository_root=collector_repository_root(Path(__file__)),
        )
        result = {"before": feed.identity_structure_diagnostics()}
        result["embedded_application_data"] = feed.embedded_application_data_diagnostics()
        if arguments.transition or arguments.refresh:
            previous = feed.current()
        if arguments.transition:
            feed.advance()
            result["candidate_confirmed"] = feed.wait_for_next(previous.shortcode) is not None
            result["after"] = feed.identity_structure_diagnostics()
            result["transition"] = asdict(feed.transition_diagnostics)
        if arguments.refresh:
            result["embedded_queue_before_refresh"] = feed.feed_queue_diagnostics()
            feed.navigate_to_reels()
            feed.current()
            result["embedded_queue_after_refresh"] = feed.feed_queue_diagnostics()
            result["embedded_application_data_after_refresh"] = (
                feed.embedded_application_data_diagnostics()
            )
        result["authenticated_json_source_classes"] = feed.feed_source_diagnostics()
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

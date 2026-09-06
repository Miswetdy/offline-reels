"""Bounded, passive modal lifecycle diagnostic; intentionally no collection ports."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from app.instagram.collector.contracts import ModalLifecycleDiagnosticResult, ModalLifecycleSnapshot
from app.instagram.collector.runtime.browser_feed import PlaywrightReelsFeed
from app.instagram.collector.runtime.errors import CollectorRuntimeError
from app.instagram.collector.runtime.settings import CollectorRuntimeSettings

_PHASES = (
    "after_chromium_launch",
    "after_reels_navigation",
    "after_readiness_wait",
    "before_collector_input",
    "after_second_wait",
)
_WAIT_SECONDS = 2.0


def run_modal_lifecycle_diagnostic(
    *, account_id: UUID, runtime: CollectorRuntimeSettings, repository_root: Path
) -> ModalLifecycleDiagnosticResult:
    """Observe one profile with fixed waits and no browser input or persistence."""
    feed: PlaywrightReelsFeed | None = None
    observations: list[tuple[str, ModalLifecycleSnapshot]] = []
    launched = False
    navigated = False
    try:
        feed = PlaywrightReelsFeed.open(
            account_id,
            runtime,
            repository_root=repository_root,
            navigate_to_reels=False,
            observe_feed_json=False,
        )
        launched = True
        observations.append((_PHASES[0], feed.modal_lifecycle_snapshot()))
        feed.navigate_to_reels()
        navigated = True
        feed.raise_if_controlled_stop()
        observations.append((_PHASES[1], feed.modal_lifecycle_snapshot()))
        feed.modal_lifecycle_wait(_WAIT_SECONDS)
        observations.append((_PHASES[2], feed.modal_lifecycle_snapshot()))
        observations.append((_PHASES[3], feed.modal_lifecycle_snapshot()))
        feed.modal_lifecycle_wait(_WAIT_SECONDS)
        observations.append((_PHASES[4], feed.modal_lifecycle_snapshot()))
        return ModalLifecycleDiagnosticResult(
            browser_launch_succeeded=launched,
            persistent_profile_configured=True,
            reels_navigation_reached=navigated,
            observation_count=len(observations),
            reason_code=None,
            observations=tuple(observations),
        )
    except CollectorRuntimeError as error:
        return ModalLifecycleDiagnosticResult(
            browser_launch_succeeded=launched,
            persistent_profile_configured=runtime.profile_root is not None,
            reels_navigation_reached=navigated,
            observation_count=len(observations),
            reason_code=error.code.value,
            observations=tuple(observations),
        )
    except Exception:
        return ModalLifecycleDiagnosticResult(
            browser_launch_succeeded=launched,
            persistent_profile_configured=runtime.profile_root is not None,
            reels_navigation_reached=navigated,
            observation_count=len(observations),
            reason_code="DIAGNOSTIC_FAILED",
            observations=tuple(observations),
        )
    finally:
        if feed is not None:
            feed.close()


def safe_modal_lifecycle_json(result: ModalLifecycleDiagnosticResult) -> str:
    """Serialize only fixed booleans, phase enums, one reason code and counts."""
    payload = {
        "browser_launch_succeeded": result.browser_launch_succeeded,
        "persistent_profile_configured": result.persistent_profile_configured,
        "reels_navigation_reached": result.reels_navigation_reached,
        "observation_count": result.observation_count,
        "reason_code": result.reason_code,
        "observations": [
            {"phase": phase, **asdict(snapshot)} for phase, snapshot in result.observations
        ],
    }
    return json.dumps(payload, sort_keys=True)


def write_modal_lifecycle_result(workspace_root: Path, payload: str) -> Path:
    """Atomically write the one redacted result to the existing workspace."""
    destination = (
        workspace_root.resolve(strict=False) / "results" / "modal-lifecycle-diagnostic.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(payload + "\n", encoding="utf-8")
    temporary.replace(destination)
    return destination

"""Regression coverage for the no-input, no-persistence modal diagnostic."""

from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from app.instagram.collector.contracts import ModalLifecycleSnapshot
from app.instagram.collector.runtime import modal_lifecycle
from app.instagram.collector.runtime.browser_feed import PlaywrightReelsFeed, TransitionLimits
from app.instagram.collector.runtime.settings import CollectorRuntimeSettings


class _PassiveFeed:
    def __init__(self) -> None:
        self.events: list[str] = []

    def modal_lifecycle_snapshot(self) -> ModalLifecycleSnapshot:
        self.events.append("snapshot")
        return ModalLifecycleSnapshot(central_video_found=True, direct_hit_start=True)

    def navigate_to_reels(self) -> None:
        self.events.append("navigate")

    def raise_if_controlled_stop(self) -> None:
        self.events.append("state")

    def modal_lifecycle_wait(self, seconds: float) -> None:
        assert seconds == 2.0
        self.events.append("wait")

    def close(self) -> None:
        self.events.append("close")


def test_modal_lifecycle_has_fixed_passive_phases_and_never_uses_input(monkeypatch, tmp_path: Path):
    passive = _PassiveFeed()
    monkeypatch.setattr(PlaywrightReelsFeed, "open", lambda *args, **kwargs: passive)
    runtime = CollectorRuntimeSettings(True, tmp_path / "profile", tmp_path / "workspace")

    result = modal_lifecycle.run_modal_lifecycle_diagnostic(
        account_id=uuid4(), runtime=runtime, repository_root=tmp_path
    )

    assert result.reason_code is None
    assert result.observation_count == 5
    assert [phase for phase, _ in result.observations] == [
        "after_chromium_launch",
        "after_reels_navigation",
        "after_readiness_wait",
        "before_collector_input",
        "after_second_wait",
    ]
    assert passive.events == [
        "snapshot",
        "navigate",
        "state",
        "snapshot",
        "wait",
        "snapshot",
        "snapshot",
        "wait",
        "snapshot",
        "close",
    ]


def test_snapshot_redacts_probe_coordinates_and_unknown_fields():
    class Page:
        closed = False

        def evaluate(self, expression):
            del expression
            return {
                "available": True,
                "in_viewport": True,
                "hit_test_start_video_observed": True,
                "hit_test_end_video_observed": False,
                "hit_test_miss_control": True,
                "hit_test_control_role_button": True,
                "x": 123,
                "start_y": 456,
                "private_dom": "never serialize",
            }

        def is_closed(self):
            return self.closed

    snapshot = PlaywrightReelsFeed(
        Page(), limits=TransitionLimits(0.1, 1, 1)
    ).modal_lifecycle_snapshot()
    values = asdict(snapshot)
    assert values["central_video_found"]
    assert values["direct_hit_start"]
    assert values["top_hit_interactive_or_control_inherited"]
    assert "x" not in values and "private_dom" not in values
    assert all(type(value) is bool for value in values.values())


def test_safe_result_has_only_allowlisted_shapes(tmp_path: Path):
    result = modal_lifecycle.ModalLifecycleDiagnosticResult(
        True,
        True,
        True,
        1,
        None,
        (("after_chromium_launch", ModalLifecycleSnapshot(central_video_found=True)),),
    )
    payload = modal_lifecycle.safe_modal_lifecycle_json(result)
    assert "coordinate" not in payload and "profile" in payload
    output = modal_lifecycle.write_modal_lifecycle_result(tmp_path, payload)
    assert output.read_text(encoding="utf-8") == payload + "\n"

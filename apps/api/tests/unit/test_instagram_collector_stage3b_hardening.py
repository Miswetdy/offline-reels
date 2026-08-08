"""Stage 3B operator hardening regressions without live services."""

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.instagram.collector.contracts import CancelRunOutcome
from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode
from app.instagram.collector.runtime.operator import (
    SafeEventTranscript,
    run_stage_3b,
    safe_summary_json,
)
from app.instagram.collector.service import CollectorSummary
from app.instagram.contracts import AccountStatus
from app.scripts import cancel_instagram_collector_run, run_instagram_collector_live
from app.scripts.verify_instagram_collector_run import main as verify_main


def test_standalone_verification_refuses_missing_pre_run_baseline(tmp_path: Path, capsys) -> None:
    result = tmp_path / "result.json"
    result.write_text(
        json.dumps({"summary": {"run_id": str(uuid4())}, "events": []}),
        encoding="utf-8",
    )
    assert verify_main([str(result)]) == 1
    output = capsys.readouterr().out
    assert "BASELINE_UNAVAILABLE" in output


def test_completed_run_with_failed_verification_returns_nonzero(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    transcript = SafeEventTranscript()
    transcript.verification = {
        "verified": False,
        "reason_code": "POST_RUN_VERIFICATION_FAILED",
    }
    summary = CollectorSummary(uuid4(), "completed", 3, 3, 0, 0, 2, None)
    runtime = SimpleNamespace(workspace_root=tmp_path)
    monkeypatch.setattr(
        run_instagram_collector_live.CollectorRuntimeSettings,
        "from_environment",
        lambda: runtime,
    )
    monkeypatch.setattr(run_instagram_collector_live, "Settings", lambda: object())
    monkeypatch.setattr(
        run_instagram_collector_live,
        "run_stage_3b",
        lambda **kwargs: (summary, transcript, "POST_RUN_VERIFICATION_FAILED"),
    )
    monkeypatch.setattr("builtins.input", lambda: "y")
    assert run_instagram_collector_live.main([]) == 1
    payload = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert payload["verification"]["verified"] is False
    assert payload["stop_reason_code"] == "POST_RUN_VERIFICATION_FAILED"


def test_safe_summary_serializes_only_aggregate_transition_diagnostics() -> None:
    transcript = SafeEventTranscript()
    transcript.transition_diagnostics = [
        {
            "position": 1,
            "scroll_attempt_count": 2,
            "poll_count": 81,
            "unchanged_sample_count": 40,
            "missing_candidate_count": 5,
            "different_candidate_observed": True,
            "stable_sample_count": 2,
            "scroll_target_available": True,
            "scroll_target_in_viewport": True,
            "mouse_move_performed": True,
            "stop_reason_code": None,
        }
    ]
    payload = json.loads(safe_summary_json(None, transcript, "TRANSITION_FAILED"))
    assert payload["transition_diagnostics"] == transcript.transition_diagnostics
    rendered = json.dumps(payload)
    assert "https://" not in rendered and "cookie" not in rendered.lower()


def test_recovery_command_has_typed_nonzero_outcomes(monkeypatch, capsys) -> None:
    class Persistence:
        def __init__(self, sessions) -> None:
            del sessions

        def cancel_run(self, run_id, reason):
            del run_id, reason
            return CancelRunOutcome.NOT_FOUND

    monkeypatch.setattr(cancel_instagram_collector_run, "CollectorPersistence", Persistence)
    monkeypatch.setattr(
        cancel_instagram_collector_run,
        "create_session_factory",
        lambda settings: None,
    )
    monkeypatch.setattr(cancel_instagram_collector_run, "Settings", lambda: object())
    assert cancel_instagram_collector_run.main([str(uuid4())]) == 1
    assert "RUN_NOT_FOUND" in capsys.readouterr().out


def test_smoke_scripts_use_application_minio_credentials_and_wait_for_readiness() -> None:
    root = next(
        (
            parent
            for parent in Path(__file__).resolve().parents
            if (parent / "scripts" / "run-collector-stage3b.ps1").is_file()
        ),
        None,
    )
    if root is None:
        pytest.skip("requires the repository-level smoke scripts")
    runner = (root / "scripts" / "run-collector-stage3b.ps1").read_text(encoding="utf-8")
    starter = (root / "scripts" / "start-collector-smoke.ps1").read_text(encoding="utf-8")
    compose = (root / "deploy" / "docker-compose.collector-smoke.yml").read_text(
        encoding="utf-8"
    )
    assert "$values['MINIO_ACCESS_KEY']" in runner
    assert "$values['MINIO_SECRET_KEY']" in runner
    assert "$values['MINIO_ROOT_USER']" not in runner
    assert "$values['MINIO_ROOT_PASSWORD']" not in runner
    for marker in (
        "postgresHealth",
        "minioHealth",
        "bootstrapState",
        "migrateState",
        "alembic current --check-heads",
        "COLLECTOR_SMOKE_POSTGRES_PORT",
        "COLLECTOR_SMOKE_MINIO_PORT",
    ):
        assert marker in starter
    assert "collector-smoke-app" in compose
    assert "s3:AbortMultipartUpload" in compose
    assert "59100" in starter
    assert "59100" in runner
    assert "59100" in compose
    assert "COLLECTOR_SMOKE_PORT_EXCLUDED" in starter


def test_readiness_failure_before_confirmation_has_safe_diagnostics_and_no_run(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []

    class Runtime:
        headless = False
        maximum_target_count = 3
        workspace_root = tmp_path
        operator_deadline_seconds = 1.0

        def require_live(self, *, repository_root: Path):
            del repository_root
            return self

    class Persistence:
        def __init__(self, sessions) -> None:
            del sessions

        def ensure_account(self, account_id) -> None:
            del account_id

        def active_run_exists(self, account_id) -> bool:
            del account_id
            return False

        def account_status(self, account_id):
            del account_id
            return AccountStatus.DISCONNECTED

        def set_account_status(self, account_id, status, reason=None) -> None:
            del account_id, status, reason

    class Feed:
        diagnostics = {
            "open_page_count": 2,
            "page_classifications": {"reels": 1, "login": 0, "challenge": 0, "other": 1},
            "video_count": 2,
            "visible_video_count": 1,
            "central_video_present": True,
            "extraction_strategy": "none",
            "reason_code": "ACTIVE_REEL_NOT_FOUND",
        }

        def current(self):
            raise CollectorRuntimeError(RuntimeReasonCode.ACTIVE_REEL_NOT_FOUND)

        def close(self) -> None:
            calls.append("close")

    monkeypatch.setattr(
        "app.instagram.collector.runtime.operator.create_session_factory",
        lambda _: object(),
    )
    monkeypatch.setattr(
        "app.instagram.collector.runtime.operator.CollectorPersistence",
        Persistence,
    )
    monkeypatch.setattr(
        "app.instagram.collector.runtime.operator.load_or_create_account_id",
        lambda _: uuid4(),
    )
    monkeypatch.setattr(
        "app.instagram.collector.runtime.operator.PlaywrightReelsFeed.open",
        lambda *args, **kwargs: Feed(),
    )
    monkeypatch.setattr(
        "app.instagram.collector.runtime.operator.create_collector_minio_client",
        lambda _: (_ for _ in ()).throw(AssertionError("MinIO must not be created before y")),
    )
    summary, transcript, reason = run_stage_3b(
        runtime=Runtime(),
        app_settings=object(),
        repository_root=tmp_path,
        confirm=lambda: (_ for _ in ()).throw(AssertionError("confirmation must not run")),
        wait_ready=lambda _: True,
    )
    assert summary is None
    assert reason == "ACTIVE_REEL_NOT_FOUND"
    assert calls == ["close"]
    payload = safe_summary_json(summary, transcript, reason)
    assert "ACTIVE_REEL_NOT_FOUND" in payload
    assert "https://" not in payload and "cookie" not in payload.lower()

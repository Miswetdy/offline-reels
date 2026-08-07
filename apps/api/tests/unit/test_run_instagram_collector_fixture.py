import json
from pathlib import Path

from app.scripts import run_instagram_collector_fixture as fixture_cli


def _summary(capsys) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)


def test_cli_happy_returns_safe_json_and_keeps_user_workspace(
    tmp_path: Path,
    capsys,
) -> None:
    workspace = tmp_path / "user-workspace"
    exit_code = fixture_cli.main(
        ["--scenario", "happy", "--target", "2", "--workspace", str(workspace)]
    )
    output = _summary(capsys)
    assert exit_code == 0
    assert output["status"] == "completed"
    assert output["confirmed_advances"] == 1
    assert str(workspace) not in json.dumps(output)
    assert "fixture-source:" not in json.dumps(output)
    assert workspace.exists()


def test_cli_repeat_with_one_workspace_is_idempotent(tmp_path: Path, capsys) -> None:
    workspace = tmp_path / "repeatable"
    assert fixture_cli.main(["--target", "2", "--workspace", str(workspace)]) == 0
    _summary(capsys)
    assert fixture_cli.main(["--target", "2", "--workspace", str(workspace)]) == 0
    output = _summary(capsys)
    assert output["source_committed_count"] == 0
    assert output["already_available_count"] == 2


def test_cli_failure_and_transition_timeout_return_nonzero_safe_results(
    tmp_path: Path,
    capsys,
) -> None:
    assert fixture_cli.main(
        ["--scenario", "download-failure", "--workspace", str(tmp_path / "failure")]
    ) == 1
    failed = _summary(capsys)
    assert failed["stop_reason_code"] == "DOWNLOAD_FAILED"
    assert "fixture download failure" not in json.dumps(failed)
    assert fixture_cli.main(
        [
            "--scenario",
            "transition-timeout",
            "--target",
            "2",
            "--workspace",
            str(tmp_path / "timeout"),
        ]
    ) == 1
    timeout = _summary(capsys)
    assert timeout["confirmed_advances"] == 0


def test_cli_owned_workspace_is_removed(monkeypatch, tmp_path: Path, capsys) -> None:
    owned = tmp_path / "owned-workspace"
    monkeypatch.setattr(fixture_cli.tempfile, "mkdtemp", lambda prefix: str(owned))
    assert fixture_cli.main(["--target", "1"]) == 0
    _summary(capsys)
    assert not owned.exists()

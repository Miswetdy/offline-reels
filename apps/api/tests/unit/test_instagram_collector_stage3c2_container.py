"""Stage 3C.2 Linux fixture boundaries that do not require Docker."""

from pathlib import Path
from uuid import uuid4

import pytest

from app.instagram.collector.contracts import ReelCandidate
from app.instagram.collector.fixtures import FixturePlaywrightNetworkGuard, SyntheticMp4Downloader
from app.instagram.collector.runtime.errors import CollectorRuntimeError
from app.instagram.collector.runtime.settings import CollectorRuntimeSettings
from app.instagram.collector.runtime.workspace import attempt_workspace, cleanup_attempt_workspace
from app.scripts.run_instagram_collector_container_fixture import _install_signal_cancellation


def test_linux_roots_are_absolute_disjoint_and_outside_checkout(tmp_path: Path) -> None:
    profile = tmp_path.parent / "profile"
    workspace = tmp_path.parent / "workspace"
    runtime = CollectorRuntimeSettings(
        enabled=True,
        profile_root=profile,
        workspace_root=workspace,
    )
    assert runtime.require_live(repository_root=tmp_path) is runtime
    nested = CollectorRuntimeSettings(True, profile, profile / "workspace")
    with pytest.raises(CollectorRuntimeError):
        nested.require_live(repository_root=tmp_path)


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_runtime_rejects_nonfinite_numeric_settings(value: str, tmp_path: Path) -> None:
    runtime = CollectorRuntimeSettings.from_environment(
        {
            "COLLECTOR_ENABLED": "true",
            "COLLECTOR_PROFILE_ROOT": str(tmp_path / "profile"),
            "COLLECTOR_WORKSPACE_ROOT": str(tmp_path / "workspace"),
            "COLLECTOR_TRANSITION_TIMEOUT_SECONDS": value,
        }
    )
    with pytest.raises(CollectorRuntimeError):
        runtime.require_live(repository_root=tmp_path / "checkout")


def test_attempt_workspace_is_owned_and_cleanup_never_removes_root(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    candidate = attempt_workspace(root, uuid4())
    (candidate / "temporary").mkdir()
    cleanup_attempt_workspace(root, candidate)
    assert root.is_dir()
    assert not candidate.exists()
    with pytest.raises(CollectorRuntimeError):
        cleanup_attempt_workspace(root, root)


def test_fixture_playwright_guard_aborts_only_http_requests() -> None:
    installed: dict[str, object] = {}

    class Context:
        def route(self, pattern, callback) -> None:
            installed["pattern"] = pattern
            installed["callback"] = callback

    class Route:
        def __init__(self) -> None:
            self.result = None

        def abort(self, value) -> None:
            self.result = ("abort", value)

        def continue_(self) -> None:
            self.result = ("continue", None)

    class Request:
        def __init__(self, url) -> None:
            self.url = url

    FixturePlaywrightNetworkGuard.install(Context())
    assert installed["pattern"] == "**/*"
    blocked, local = Route(), Route()
    installed["callback"](blocked, Request("https://www.instagram.com/reel/x/"))
    installed["callback"](local, Request("file:///fixture.html"))
    assert blocked.result == ("abort", "blockedbyclient")
    assert local.result == ("continue", None)


def test_synthetic_downloader_has_no_candidate_url_or_network_arguments(
    monkeypatch, tmp_path: Path
) -> None:
    captured: list[str] = []

    def fake_run(command, **kwargs) -> None:
        captured.extend(command)
        assert kwargs["stdin"] is not None

    monkeypatch.setattr("app.instagram.collector.fixtures.subprocess.run", fake_run)
    SyntheticMp4Downloader().download(
        ReelCandidate("FIXTURE", "https://www.instagram.com/reel/FIXTURE/"),
        tmp_path / "fixture.part",
    )
    assert "https://www.instagram.com/reel/FIXTURE/" not in captured
    assert not any(item.startswith(("http://", "https://")) for item in captured)


def test_sigterm_handler_cooperatively_cancels_the_active_engine(monkeypatch) -> None:
    handlers = {}
    monkeypatch.setattr(
        "app.scripts.run_instagram_collector_container_fixture.signal.signal",
        handlers.__setitem__,
    )
    _install_signal_cancellation()
    with pytest.raises(KeyboardInterrupt):
        handlers[15](15, None)

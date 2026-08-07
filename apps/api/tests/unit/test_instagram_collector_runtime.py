# ruff: noqa: E501

import shutil
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.instagram.collector.contracts import ReelCandidate
from app.instagram.collector.runtime.browser_feed import (
    IDENTITY_PROBE,
    PAUSE_PROBE,
    STATE_PROBE,
    PlaywrightReelsFeed,
    TransitionLimits,
)
from app.instagram.collector.runtime.downloader import (
    PythonYtDlpFacade,
    SessionFirstYtDlpDownloader,
    _format_selector,
    build_yt_dlp_options,
)
from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode
from app.instagram.collector.runtime.minio_storage import MinioCollectorSourceStorage
from app.instagram.collector.runtime.profile_lock import ProfileLock, profile_path
from app.instagram.collector.runtime.session_cookies import SessionCookieProvider
from app.instagram.collector.runtime.settings import CollectorRuntimeSettings
from app.instagram.collector.runtime.validator import FfprobeSourceValidator
from app.media.models import MediaProbe


def candidate(code: str = "SAFE_CODE") -> ReelCandidate:
    return ReelCandidate(code, f"https://www.instagram.com/reel/{code}/")


class FakePage:
    def __init__(self, candidates: list[ReelCandidate], *, state: dict[str, bool] | None = None) -> None:
        self._candidates = candidates
        self._index = 0
        self._state = state or {"login": False, "checkpoint": False, "limited": False}
        self.pause_calls = 0
        self.scroll_calls = 0
        self.closed = False

    def evaluate(self, expression: str):
        if expression == IDENTITY_PROBE:
            current = self._candidates[self._index]
            return {"shortcode": current.shortcode, "canonical_url": current.canonical_url}
        if expression == PAUSE_PROBE:
            self.pause_calls += 1
            return True
        if expression == STATE_PROBE:
            return self._state
        if "scrollBy" in expression:
            self.scroll_calls += 1
            if self._index < len(self._candidates) - 1:
                self._index += 1
            return None
        raise AssertionError("Unexpected browser evaluation")

    def goto(self, url: str, *, wait_until: str):
        del url, wait_until

    def wait_for_timeout(self, timeout: float) -> None:
        del timeout

    def is_closed(self) -> bool:
        return self.closed


def feed(page: FakePage) -> PlaywrightReelsFeed:
    return PlaywrightReelsFeed(
        page,
        limits=TransitionLimits(polling_seconds=0.01, timeout_seconds=0.03, maximum_scroll_attempts=2),
    )


def test_browser_feed_confirms_two_stable_samples_and_pauses_only_current() -> None:
    page = FakePage([candidate("ONE"), candidate("TWO")])
    adapter = feed(page)
    assert adapter.current().shortcode == "ONE"
    adapter.pause_current()
    adapter.advance()
    assert adapter.wait_for_next("ONE").shortcode == "TWO"  # type: ignore[union-attr]
    assert page.pause_calls == 1
    assert page.scroll_calls == 1


def test_browser_feed_timeout_and_controlled_stops_are_safe() -> None:
    adapter = feed(FakePage([candidate("ONE")]))
    adapter.advance()
    assert adapter.wait_for_next("ONE") is None
    auth = feed(FakePage([candidate()], state={"login": True, "checkpoint": False, "limited": False}))
    with pytest.raises(CollectorRuntimeError) as error:
        auth.current()
    assert error.value.code is RuntimeReasonCode.AUTH_REQUIRED
    invalid = feed(
        FakePage(
            [
                candidate("ONE"),
                ReelCandidate("BAD.CODE", "https://www.instagram.com/reel/BAD.CODE/"),
            ]
        )
    )
    invalid.advance()
    with pytest.raises(CollectorRuntimeError) as error:
        invalid.wait_for_next("ONE")
    assert error.value.code is RuntimeReasonCode.INVALID_REEL_CANDIDATE


def test_cookie_provider_filters_to_minimal_secure_instagram_jar() -> None:
    context = _CookieContext(
        [
            _cookie("sessionid", "secret-session", ".instagram.com"),
            _cookie("csrftoken", "secret-csrf", "www.instagram.com"),
            _cookie("sessionid", "expired", ".instagram.com", expires=1),
            _cookie("sessionid", "foreign", "instagram.com.evil.example"),
            _cookie("other", "secret-other", ".instagram.com"),
        ]
    )
    jar = SessionCookieProvider().get(context)
    assert "secret-session" not in repr(jar)
    assert "secret-csrf" not in repr(jar)
    assert {cookie.name for cookie in jar.to_http_cookiejar()} == {"sessionid", "csrftoken"}
    jar.clear()
    assert list(jar.to_http_cookiejar()) == []


def test_cookie_provider_requires_session_cookie() -> None:
    with pytest.raises(CollectorRuntimeError) as error:
        SessionCookieProvider().get(_CookieContext([_cookie("csrftoken", "value", ".instagram.com")]))
    assert error.value.code is RuntimeReasonCode.AUTH_REQUIRED


def test_session_first_downloader_never_creates_an_anonymous_attempt(tmp_path: Path) -> None:
    output = tmp_path / "temporary" / "SAFE_CODE.part"
    facade = _DownloaderFacade()
    jar = SessionCookieProvider().get(_CookieContext([_cookie("sessionid", "secret", ".instagram.com")]))
    SessionFirstYtDlpDownloader(jar, maximum_bytes=1024, facade=facade).download(candidate(), output)
    assert output.read_bytes() == b"fixture-media"
    assert facade.calls == 1
    assert "secret" not in repr(facade)
    assert list(jar.to_http_cookiejar()) == []
    selector = _format_selector()
    assert "vcodec^=avc1" in selector and "acodec^=mp4a" in selector
    assert "bestvideo" in selector and "+bestaudio" in selector
    options = build_yt_dlp_options("safe-template", 1024)
    assert options["noplaylist"] is True and options["playlistend"] == 1
    assert not {"cookiefile", "cookiesfrombrowser", "http_headers"} & set(options)


def test_session_first_downloader_cleans_partial_and_redacts_failure(tmp_path: Path) -> None:
    output = tmp_path / "temporary" / "SAFE_CODE.part"
    jar = SessionCookieProvider().get(_CookieContext([_cookie("sessionid", "secret", ".instagram.com")]))
    with pytest.raises(CollectorRuntimeError) as error:
        SessionFirstYtDlpDownloader(jar, maximum_bytes=1024, facade=_DownloaderFacade(fail=True)).download(
            candidate(), output
        )
    assert error.value.code is RuntimeReasonCode.DOWNLOAD_FAILED
    assert not output.exists()
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("fail", [False, True])
def test_python_yt_dlp_facade_clears_attempt_local_http_cookie_jar(tmp_path: Path, fail: bool) -> None:
    captured: list[object] = []
    output = tmp_path / "temporary" / "SAFE_CODE.part"
    jar = SessionCookieProvider().get(_CookieContext([_cookie("sessionid", "secret", ".instagram.com")]))

    def factory(options: dict[str, object]) -> _FakeYoutubeDL:
        return _FakeYoutubeDL(options, captured, fail=fail)

    facade = PythonYtDlpFacade(factory)
    if fail:
        with pytest.raises(RuntimeError):
            facade.download(candidate(), jar, output, 1024)
    else:
        facade.download(candidate(), jar, output, 1024)
        assert output.read_bytes() == b"fixture-media"
    assert captured
    assert list(captured[0]) == []
    assert "secret" not in repr(captured[0])


def test_validator_uses_ffprobe_and_rejects_non_mp4_or_video_only(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    temporary = workspace / "temporary"
    temporary.mkdir(parents=True)
    combined = temporary / "combined.mp4"
    video_only = temporary / "video-only.mp4"
    matroska = temporary / "source.mkv"
    disguised = temporary / "masquerading.mp4"
    _ffmpeg_fixture(combined, audio=True)
    _ffmpeg_fixture(video_only, audio=False)
    _ffmpeg_fixture(matroska, audio=True)
    shutil.copy2(matroska, disguised)
    validator = FfprobeSourceValidator(workspace, 10 * 1024 * 1024)
    result = validator.validate(combined)
    assert result.content_type == "video/mp4"
    assert result.byte_size == combined.stat().st_size
    with pytest.raises(CollectorRuntimeError) as error:
        validator.validate(video_only)
    assert error.value.code is RuntimeReasonCode.VALIDATION_FAILED
    with pytest.raises(CollectorRuntimeError) as error:
        validator.validate(disguised)
    assert error.value.code is RuntimeReasonCode.VALIDATION_FAILED


def test_validator_rejects_missing_container_format_name(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    temporary = workspace / "temporary" / "source.mp4"
    temporary.parent.mkdir(parents=True)
    temporary.write_bytes(b"fixture")
    unknown_container = MediaProbe(
        path=temporary,
        video_codec="h264",
        pixel_format="yuv420p",
        audio_codecs=("aac",),
        duration_seconds=1.0,
        width=1,
        height=1,
    )
    with patch("app.instagram.collector.runtime.validator.probe_media", return_value=unknown_container):
        with pytest.raises(CollectorRuntimeError) as error:
            FfprobeSourceValidator(workspace, 1024).validate(temporary)
    assert error.value.code is RuntimeReasonCode.VALIDATION_FAILED


def test_minio_storage_is_prefix_bound_and_idempotent(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    path = workspace / "temporary" / "SAFE_CODE.part"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"source")
    client = _MemoryMinio()
    storage = MinioCollectorSourceStorage(client, "offline-reels", workspace, 1024)
    created = storage.publish(path, "instagram-sources/SAFE_CODE.mp4")
    assert created.created_by_attempt is True
    existing = storage.publish(path, "instagram-sources/SAFE_CODE.mp4")
    assert existing.created_by_attempt is False
    storage.delete("instagram-sources/SAFE_CODE.mp4")
    with pytest.raises(CollectorRuntimeError):
        storage.delete("videos/SAFE_CODE.mp4")


def test_profile_lock_and_runtime_settings_are_conservative(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    workspace = tmp_path / "workspace"
    account_id = uuid4()
    profile = profile_path(profiles, account_id)
    first = ProfileLock(profile)
    first.acquire()
    with pytest.raises(CollectorRuntimeError) as error:
        ProfileLock(profile).acquire()
    assert error.value.code is RuntimeReasonCode.PROFILE_IN_USE
    first.release()
    first.release()
    settings = CollectorRuntimeSettings(True, profiles, workspace)
    assert settings.require_live(repository_root=tmp_path / "repo") is settings
    with pytest.raises(CollectorRuntimeError):
        CollectorRuntimeSettings(False, profiles, workspace).require_live(repository_root=tmp_path / "repo")
    with pytest.raises(CollectorRuntimeError):
        CollectorRuntimeSettings(True, profiles, profiles).require_live(repository_root=tmp_path / "repo")


def test_profile_lock_maps_filesystem_acquire_error_to_safe_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = ProfileLock(tmp_path / "profile")
    monkeypatch.setattr(
        "app.instagram.collector.runtime.profile_lock.os.open",
        lambda *args: (_ for _ in ()).throw(OSError("sensitive filesystem failure")),
    )
    with pytest.raises(CollectorRuntimeError) as error:
        lock.acquire()
    assert error.value.code is RuntimeReasonCode.PROFILE_IN_USE
    assert "sensitive" not in str(error.value)


def test_runtime_settings_rejects_repository_and_overlapping_roots(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    external = tmp_path / "external"
    profiles = external / "profiles"
    workspace = external / "workspace"
    assert CollectorRuntimeSettings(True, profiles, workspace).require_live(repository_root=repository)
    for profile, work in (
        (repository / "collector-profile", workspace),
        (profiles, repository / "collector-workspace"),
        (profiles, profiles),
        (profiles, profiles / "workspace"),
    ):
        with pytest.raises(CollectorRuntimeError) as error:
            CollectorRuntimeSettings(True, profile, work).require_live(repository_root=repository)
        assert error.value.code is RuntimeReasonCode.COLLECTOR_DISABLED


def test_runtime_settings_resolves_symlink_before_repository_containment_check(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    link = tmp_path / "outside-link"
    try:
        link.symlink_to(repository, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")
    with pytest.raises(CollectorRuntimeError) as error:
        CollectorRuntimeSettings(True, link / "profiles", tmp_path / "workspace").require_live(
            repository_root=repository
        )
    assert error.value.code is RuntimeReasonCode.COLLECTOR_DISABLED


def test_browser_close_is_best_effort_and_idempotent() -> None:
    context = _CloseFailureContext()
    playwright = _CloseFailurePlaywright()
    lock = _LockSpy()
    adapter = PlaywrightReelsFeed(
        FakePage([candidate()]),
        limits=TransitionLimits(0.01, 0.03, 2),
        context=context,
        playwright=playwright,
        profile_lock=lock,  # type: ignore[arg-type]
    )
    adapter.close()
    adapter.close()
    assert context.close_calls == 1
    assert playwright.stop_calls == 1
    assert lock.release_calls == 1


def test_browser_open_preserves_controlled_stop_despite_cleanup_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.instagram.collector.runtime import browser_feed

    page = FakePage([candidate()], state={"login": True, "checkpoint": False, "limited": False})
    context = _OpenFailureContext(page)
    playwright = _OpenFailurePlaywright(context)
    lock = _LockSpy()
    monkeypatch.setattr(browser_feed, "ProfileLock", lambda profile: lock)
    monkeypatch.setitem(
        sys.modules,
        "playwright.sync_api",
        types.SimpleNamespace(sync_playwright=lambda: _SyncStarter(playwright)),
    )
    settings = CollectorRuntimeSettings(True, tmp_path / "profiles", tmp_path / "workspace")
    with pytest.raises(CollectorRuntimeError) as error:
        PlaywrightReelsFeed.open(uuid4(), settings, repository_root=tmp_path / "repository")
    assert error.value.code is RuntimeReasonCode.AUTH_REQUIRED
    assert context.close_calls == 1
    assert playwright.stop_calls == 1
    assert lock.release_calls == 1


class _CookieContext:
    def __init__(self, cookies: list[dict[str, object]]) -> None:
        self._cookies = cookies

    def cookies(self) -> list[dict[str, object]]:
        return self._cookies


def _cookie(name: str, value: str, domain: str, *, expires: float = -1) -> dict[str, object]:
    return {
        "name": name,
        "value": value,
        "domain": domain,
        "path": "/",
        "secure": True,
        "expires": expires,
    }


class _DownloaderFacade:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self._fail = fail

    def download(self, reel, cookie_jar, temporary_path: Path, maximum_bytes: int) -> None:
        del reel, cookie_jar, maximum_bytes
        self.calls += 1
        temporary_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_bytes(b"partial")
        if self._fail:
            raise RuntimeError("https://cdn.example.invalid/signed-secret")
        temporary_path.write_bytes(b"fixture-media")


class _FakeYoutubeDL:
    def __init__(self, options: dict[str, object], captured: list[object], *, fail: bool) -> None:
        self._template = str(options["outtmpl"])
        self._captured = captured
        self._fail = fail
        self.cookiejar = None

    def __enter__(self) -> _FakeYoutubeDL:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        del exc_type, exc_value, traceback

    def extract_info(self, url: str, *, download: bool) -> None:
        del url, download
        self._captured.append(self.cookiejar)
        if self._fail:
            raise RuntimeError("https://cdn.example.invalid/signed-secret")
        Path(self._template.replace("%(ext)s", "mp4")).write_bytes(b"fixture-media")


class _CloseFailureContext:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1
        raise OSError("sensitive close failure")


class _CloseFailurePlaywright:
    def __init__(self) -> None:
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1
        raise OSError("sensitive stop failure")


class _LockSpy:
    def __init__(self) -> None:
        self.acquire_calls = 0
        self.release_calls = 0

    def acquire(self) -> None:
        self.acquire_calls += 1

    def release(self) -> None:
        self.release_calls += 1
        raise OSError("sensitive lock release failure")


class _OpenFailureContext(_CloseFailureContext):
    def __init__(self, page: FakePage) -> None:
        super().__init__()
        self.pages = [page]


class _OpenFailurePlaywright(_CloseFailurePlaywright):
    def __init__(self, context: _OpenFailureContext) -> None:
        super().__init__()
        self.chromium = types.SimpleNamespace(launch_persistent_context=lambda profile, headless: context)


class _SyncStarter:
    def __init__(self, playwright: _OpenFailurePlaywright) -> None:
        self._playwright = playwright

    def start(self) -> _OpenFailurePlaywright:
        return self._playwright


class _MissingObject(Exception):
    code = "NoSuchKey"


class _MemoryMinio:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def stat_object(self, bucket_name: str, object_name: str):
        del bucket_name
        if object_name not in self.objects:
            raise _MissingObject()
        return object()

    def fput_object(self, bucket_name: str, object_name: str, file_path: str, *, content_type: str):
        del bucket_name, content_type
        self.objects[object_name] = Path(file_path).read_bytes()

    def remove_object(self, bucket_name: str, object_name: str):
        del bucket_name
        self.objects.pop(object_name, None)


def _ffmpeg_fixture(path: Path, *, audio: bool) -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.fail("ffmpeg and ffprobe are required for Collector validator tests")
    command = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=24"]
    if audio:
        command.extend(["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100"])
    command.extend(["-t", "0.5", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p"])
    if audio:
        command.extend(["-c:a", "aac"])
    subprocess.run([*command, str(path)], check=True)

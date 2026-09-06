# ruff: noqa: E501

import os
import shutil
import subprocess
import sys
import types
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.instagram.collector.contracts import ReelCandidate
from app.instagram.collector.runtime.browser_feed import (
    ACTIVE_FEED_INPUT_TARGET_PROBE,
    ACTIVE_MEDIA_IDENTITY_PROBE,
    EMBEDDED_APPLICATION_CANDIDATES_PROBE,
    EMBEDDED_APPLICATION_DATA_PROBE,
    IDENTITY_PROBE,
    IDENTITY_STRUCTURE_PROBE,
    PAUSE_PROBE,
    SCROLL_CONTAINER_PROBE,
    SCROLL_TARGET_PROBE,
    STATE_PROBE,
    PlaywrightReelsFeed,
    TransitionLimits,
)
from app.instagram.collector.runtime.downloader import (
    FreshSessionFirstYtDlpDownloader,
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
    def __init__(
        self,
        candidates: list[ReelCandidate],
        *,
        state: dict[str, bool] | None = None,
        transition_samples: list[ReelCandidate | None] | None = None,
        scroll_target: dict[str, object] | None = None,
        scroll_container: bool = False,
        media_identity_samples: list[str] | None = None,
        embedded_codes: list[str] | None = None,
        refresh_embedded_codes: list[str] | None = None,
        transition_response_code: str | None = None,
        emit_transition_response: bool = True,
    ) -> None:
        self._candidates = candidates
        self._index = 0
        self._state = state or {"login": False, "checkpoint": False, "limited": False}
        self.pause_calls = 0
        self.mouse = _FakeMouse(self)
        self.closed = False
        self._transition_samples = list(transition_samples or [])
        self._scroll_target = scroll_target or {
            "available": True,
            "in_viewport": True,
            "x": 100.0,
            "y": 200.0,
            "width": 800.0,
            "height": 600.0,
        }
        self._scroll_container = scroll_container
        self._active_feed_target = {
            "available": scroll_container,
            "in_viewport": scroll_container,
            "hit_testable": scroll_container,
            "x": 400.0,
            "start_y": 430.0,
            "end_y": 120.0,
        }
        self._media_identity_samples = list(media_identity_samples or [])
        self._embedded_codes = list(embedded_codes or [])
        self._refresh_embedded_codes = list(refresh_embedded_codes or [])
        self._transition_response_code = transition_response_code
        self._emit_transition_response = emit_transition_response
        self._input_performed = False
        self._response_handler = None
        self.url = "https://www.instagram.com/reels/"

    def on(self, event, handler) -> None:
        assert event == "response"
        self._response_handler = handler

    def evaluate(self, expression: str):
        if expression == IDENTITY_PROBE:
            if self.mouse.calls and self._transition_samples:
                sampled = self._transition_samples.pop(0)
                if sampled is None:
                    return {"video_count": 1, "visible_video_count": 0}
                return {"shortcode": sampled.shortcode, "canonical_url": sampled.canonical_url}
            current = self._candidates[self._index]
            return {"shortcode": current.shortcode, "canonical_url": current.canonical_url}
        if expression == IDENTITY_STRUCTURE_PROBE:
            return {
                "video_count": 4,
                "visible_video_count": 1,
                "central_video_present": True,
                "page_reel_anchor_count": 0,
                "nearby_reel_anchor_count": 0,
                "ancestor_data_attribute_count": 3,
                "bound_canonical_data_attribute_count": 1,
                "bound_canonical_data_attribute_changed": True,
                "location_is_specific_reel": False,
                "href": "must-not-leak",
            }
        if expression == EMBEDDED_APPLICATION_DATA_PROBE:
            return {
                "embedded_json_script_count": 2,
                "parseable_embedded_json_script_count": 1,
                "oversized_embedded_json_script_count": 1,
                "embedded_tree_allowed_canonical_alias_values": 3,
                "embedded_media_descendant_allowed_canonical_alias_values": 2,
            }
        if expression == EMBEDDED_APPLICATION_CANDIDATES_PROBE:
            return list(self._embedded_codes)
        if expression == PAUSE_PROBE:
            self.pause_calls += 1
            return True
        if expression == SCROLL_TARGET_PROBE:
            return self._scroll_target
        if expression == SCROLL_CONTAINER_PROBE:
            return self._scroll_container
        if expression == ACTIVE_FEED_INPUT_TARGET_PROBE:
            return self._active_feed_target
        if expression == ACTIVE_MEDIA_IDENTITY_PROBE:
            if self._media_identity_samples:
                return self._media_identity_samples.pop(0)
            if self._input_performed:
                return "media-two"
            return "media-one"
        if expression == STATE_PROBE:
            return self._state
        raise AssertionError("Unexpected browser evaluation")

    def goto(self, url: str, *, wait_until: str):
        del url, wait_until
        self._embedded_codes = list(self._refresh_embedded_codes)

    def wait_for_timeout(self, timeout: float) -> None:
        del timeout

    def is_closed(self) -> bool:
        return self.closed

    def complete_input(self) -> None:
        self._input_performed = True
        if self._index < len(self._candidates) - 1:
            self._index += 1
            if self._response_handler is not None and self._emit_transition_response:
                self._response_handler(
                    _JsonResponse(self._transition_response_code or self._candidates[self._index].shortcode)
                )


def feed(page: FakePage) -> PlaywrightReelsFeed:
    return PlaywrightReelsFeed(
        page,
        limits=TransitionLimits(polling_seconds=0.01, timeout_seconds=0.03, maximum_scroll_attempts=2),
    )


class _LiveLikeContext:
    def __init__(self, page: FakePage) -> None:
        self.pages = [page]

    def close(self) -> None:
        return None


def test_browser_feed_confirms_two_stable_samples_and_pauses_only_current() -> None:
    page = FakePage([candidate("ONE"), candidate("TWO")])
    adapter = feed(page)
    assert adapter.current().shortcode == "ONE"
    adapter.pause_current()
    adapter.advance()
    assert adapter.wait_for_next("ONE").shortcode == "TWO"  # type: ignore[union-attr]
    assert page.pause_calls == 1
    assert page.mouse.moves == [(400.0, 300.0)]
    assert page.mouse.calls == [(0, 540)]
    assert page.mouse.actions == [("move", 400.0, 300.0), ("wheel", 0, 540)]


def test_browser_feed_uses_embedded_queue_after_stable_transition() -> None:
    page = FakePage(
        [candidate("ONE"), candidate("TWO")],
        embedded_codes=["TWO"],
        transition_response_code="INVALID.CODE",
        transition_samples=[None, None, None],
    )
    adapter = feed(page)

    assert adapter.current().shortcode == "ONE"
    adapter.advance()

    next_candidate = adapter.wait_for_next("ONE")
    assert next_candidate is not None and next_candidate.shortcode == "TWO"
    assert adapter.transition_diagnostics.canonical_queue_fallback_observed


def test_browser_feed_uses_embedded_queue_without_post_input_json() -> None:
    page = FakePage(
        [candidate("ONE"), candidate("TWO")],
        embedded_codes=["TWO"],
        emit_transition_response=False,
        transition_samples=[None, None, None],
    )
    adapter = feed(page)

    assert adapter.current().shortcode == "ONE"
    adapter.advance()

    next_candidate = adapter.wait_for_next("ONE")
    assert next_candidate is not None and next_candidate.shortcode == "TWO"
    assert not adapter.transition_diagnostics.post_action_json_observed
    assert adapter.transition_diagnostics.canonical_queue_fallback_observed


def test_browser_feed_reserves_embedded_candidate_without_page_input() -> None:
    page = FakePage([candidate("ONE")], embedded_codes=["TWO"])
    adapter = PlaywrightReelsFeed(
        page,
        context=_LiveLikeContext(page),
        limits=TransitionLimits(polling_seconds=0.01, timeout_seconds=0.03, maximum_scroll_attempts=2),
    )

    assert adapter.current().shortcode == "ONE"
    next_candidate = adapter.next_from_authenticated_feed("ONE")

    assert next_candidate is not None and next_candidate.shortcode == "TWO"
    assert page.mouse.actions == []


def test_browser_feed_refreshes_only_after_stable_transition_and_empty_queue() -> None:
    page = FakePage(
        [candidate("ONE"), candidate("TWO")],
        refresh_embedded_codes=["THREE"],
        emit_transition_response=False,
    )
    adapter = PlaywrightReelsFeed(
        page,
        context=_LiveLikeContext(page),
        limits=TransitionLimits(polling_seconds=0.01, timeout_seconds=0.03, maximum_scroll_attempts=2),
    )

    assert adapter.current().shortcode == "ONE"
    adapter.advance()

    next_candidate = adapter.wait_for_next("ONE")
    assert next_candidate is not None and next_candidate.shortcode == "THREE"
    assert adapter.transition_diagnostics.canonical_feed_refresh_observed


def test_browser_feed_replenishes_after_consuming_the_initial_embedded_queue() -> None:
    page = FakePage(
        [candidate("ONE"), candidate("TWO"), candidate("THREE")],
        embedded_codes=["TWO"],
        refresh_embedded_codes=["FOUR"],
        emit_transition_response=False,
        media_identity_samples=[
            "media-one",
            "media-two",
            "media-two",
            "media-two",
            "media-three",
            "media-three",
        ],
    )
    adapter = PlaywrightReelsFeed(
        page,
        context=_LiveLikeContext(page),
        limits=TransitionLimits(polling_seconds=0.01, timeout_seconds=0.03, maximum_scroll_attempts=3),
    )

    assert adapter.current().shortcode == "ONE"
    adapter.advance()
    first = adapter.wait_for_next("ONE")
    assert first is not None and first.shortcode == "TWO"
    assert adapter.transition_diagnostics.canonical_queue_fallback_observed

    adapter.advance()
    second = adapter.wait_for_next(first.shortcode)
    assert second is not None and second.shortcode == "FOUR"
    assert adapter.transition_diagnostics.canonical_feed_refresh_observed


def test_browser_feed_uses_bounded_pointer_wheel_when_scroll_container_is_unavailable() -> None:
    page = FakePage([candidate()])
    context = _CdpContext()
    adapter = PlaywrightReelsFeed(
        page,
        limits=TransitionLimits(polling_seconds=0.01, timeout_seconds=0.03, maximum_scroll_attempts=2),
        context=context,
    )

    adapter.advance()

    assert page.mouse.actions == [("move", 400.0, 300.0), ("wheel", 0, 540)]
    assert context.session.commands == []
    assert context.session.detach_calls == 0


def test_browser_feed_prefers_scroll_owner_and_confirms_stable_media_change() -> None:
    page = FakePage(
        [candidate("ONE")],
        scroll_container=True,
        media_identity_samples=["media-one", "media-two", "media-two"],
    )

    context = _CdpContext(page)
    PlaywrightReelsFeed(
        page,
        context=context,
        limits=TransitionLimits(polling_seconds=0.01, timeout_seconds=0.03, maximum_scroll_attempts=2),
    ).advance()

    assert page.mouse.actions == []
    assert [params["type"] for _, params in context.session.commands] == [
        "touchStart", "touchMove", "touchEnd"
    ]


def test_browser_feed_forces_pointer_retry_when_media_change_has_no_new_reel() -> None:
    page = FakePage(
        [candidate("ONE")],
        scroll_container=True,
        media_identity_samples=["media-one", "media-two", "media-two"],
    )
    adapter = PlaywrightReelsFeed(
        page,
        context=_CdpContext(page),
        limits=TransitionLimits(polling_seconds=0.01, timeout_seconds=0.03, maximum_scroll_attempts=2),
    )

    adapter.advance()
    assert page.mouse.actions == []
    assert adapter.wait_for_next("ONE") is None

    adapter.advance()
    assert page.mouse.actions == [("move", 400.0, 300.0), ("wheel", 0, 540)]


def test_identity_structure_diagnostics_are_aggregate_only() -> None:
    result = feed(FakePage([candidate()])).identity_structure_diagnostics()
    assert result == {
        "video_count": 4,
        "visible_video_count": 1,
        "central_video_present": True,
        "page_reel_anchor_count": 0,
        "nearby_reel_anchor_count": 0,
        "ancestor_data_attribute_count": 3,
        "bound_canonical_data_attribute_count": 1,
        "bound_canonical_data_attribute_changed": True,
        "location_is_specific_reel": False,
    }


def test_embedded_application_data_diagnostics_are_aggregate_only() -> None:
    assert feed(FakePage([candidate()])).embedded_application_data_diagnostics() == {
        "embedded_json_script_count": 2,
        "parseable_embedded_json_script_count": 1,
        "oversized_embedded_json_script_count": 1,
        "embedded_tree_allowed_canonical_alias_values": 3,
        "embedded_media_descendant_allowed_canonical_alias_values": 2,
    }


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
    assert invalid.wait_for_next("ONE") is None


def test_browser_feed_wheel_close_is_a_safe_browser_closed_stop() -> None:
    page = FakePage([candidate("ONE")])
    page.mouse.close_on_wheel = True
    with pytest.raises(CollectorRuntimeError) as error:
        feed(page).advance()
    assert error.value.code is RuntimeReasonCode.BROWSER_CLOSED


@pytest.mark.parametrize(
    "target",
    [
        {"available": False, "in_viewport": False},
        {"available": True, "in_viewport": True, "x": float("nan"), "y": 1, "width": 2, "height": 2},
        {"available": True, "in_viewport": True, "x": float("inf"), "y": 1, "width": 2, "height": 2},
        {"available": True, "in_viewport": False, "x": 900, "y": 1, "width": 800, "height": 600},
    ],
)
def test_browser_feed_rejects_missing_or_invalid_scroll_targets(target: dict[str, object]) -> None:
    page = FakePage([candidate("ONE")], scroll_target=target)
    with pytest.raises(CollectorRuntimeError) as error:
        feed(page).advance()
    assert error.value.code is RuntimeReasonCode.ACTIVE_REEL_NOT_FOUND
    assert page.mouse.moves == []
    assert page.mouse.calls == []


def test_pointer_wheel_uses_viewport_centre_after_target_validation() -> None:
    first = {"available": True, "in_viewport": True, "x": 400, "y": 250, "width": 800, "height": 600}
    second = {"available": True, "in_viewport": True, "x": 300, "y": 100, "width": 600, "height": 400}
    page = FakePage([candidate("ONE")], scroll_target=first)
    adapter = feed(page)
    adapter.advance()
    page._scroll_target = second
    adapter.advance()
    assert page.mouse.actions == [
        ("move", 400.0, 300.0), ("wheel", 0, 540),
        ("move", 300.0, 200.0), ("wheel", 0, 360),
    ]
    assert adapter.scroll_target_diagnostics.mouse_move_performed


def test_browser_feed_stabilizes_a_different_reel_before_permitting_retry() -> None:
    page = FakePage(
        [candidate("ONE"), candidate("TWO")],
        transition_samples=[candidate("TWO"), None, candidate("TWO"), candidate("TWO")],
    )
    adapter = PlaywrightReelsFeed(
        page,
        limits=TransitionLimits(
            polling_seconds=0.01,
            timeout_seconds=0.02,
            maximum_scroll_attempts=2,
            stabilization_seconds=0.02,
        ),
    )
    adapter.advance()
    assert adapter.wait_for_next("ONE").shortcode == "TWO"  # type: ignore[union-attr]
    assert page.mouse.calls == [(0, 540)]
    assert adapter.transition_diagnostics.poll_count == 2
    assert adapter.transition_diagnostics.different_candidate_observed
    assert adapter.transition_diagnostics.stable_sample_count == 2
    assert adapter.transition_diagnostics.post_action_json_observed


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
    assert {cookie.name for cookie in jar.to_ytdlp_cookiejar()} == {"sessionid", "csrftoken"}
    jar.clear()
    assert list(jar.to_ytdlp_cookiejar()) == []


def test_cookie_provider_requires_session_cookie() -> None:
    with pytest.raises(CollectorRuntimeError) as error:
        SessionCookieProvider().get(_CookieContext([_cookie("csrftoken", "value", ".instagram.com")]))
    assert error.value.code is RuntimeReasonCode.SESSION_COOKIE_MISSING


def test_session_first_downloader_never_creates_an_anonymous_attempt(tmp_path: Path) -> None:
    output = tmp_path / "temporary" / "SAFE_CODE.part"
    facade = _DownloaderFacade()
    jar = SessionCookieProvider().get(_CookieContext([_cookie("sessionid", "secret", ".instagram.com")]))
    SessionFirstYtDlpDownloader(jar, maximum_bytes=1024, facade=facade).download(candidate(), output)
    assert output.read_bytes() == b"fixture-media"
    assert facade.calls == 1
    assert "secret" not in repr(facade)
    assert list(jar.to_ytdlp_cookiejar()) == []
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
def test_python_yt_dlp_facade_clears_attempt_local_ytdlp_cookie_jar(tmp_path: Path, fail: bool) -> None:
    captured: list[object] = []
    output = tmp_path / "temporary" / "SAFE_CODE.part"
    jar = SessionCookieProvider().get(_CookieContext([_cookie("sessionid", "secret", ".instagram.com")]))

    def factory(options: dict[str, object]) -> _FakeYoutubeDL:
        return _FakeYoutubeDL(options, captured, fail=fail)

    facade = PythonYtDlpFacade(factory)
    if fail:
        with pytest.raises(CollectorRuntimeError) as error:
            facade.download(candidate(), jar, output, 1024)
        assert error.value.code is RuntimeReasonCode.DOWNLOAD_FAILED
    else:
        facade.download(candidate(), jar, output, 1024)
        assert output.read_bytes() == b"fixture-media"
    assert captured
    assert list(captured[0]) == []


@pytest.mark.skipif(os.name != "posix", reason="SIGALRM download deadline is Linux-only")
def test_python_yt_dlp_facade_applies_a_hard_download_deadline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.instagram.collector.runtime import downloader as runtime_downloader

    class BlockingYoutubeDL:
        def __init__(self, _options: dict[str, object]) -> None:
            self.cookiejar = None

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def extract_info(self, _url: str, *, download: bool) -> None:
            assert download is True
            import time

            time.sleep(1)

    monkeypatch.setattr(runtime_downloader, "MAX_DOWNLOAD_SECONDS", 0.01)
    jar = SessionCookieProvider().get(
        _CookieContext([_cookie("sessionid", "secret", ".instagram.com")])
    )
    with pytest.raises(CollectorRuntimeError) as error:
        PythonYtDlpFacade(BlockingYoutubeDL).download(candidate(), jar, tmp_path / "output.mp4", 1024)
    assert error.value.code is RuntimeReasonCode.DIRECT_DOWNLOAD_TIMEOUT


def test_python_yt_dlp_facade_uses_spike_attempt_directory_and_native_cookiejar(
    tmp_path: Path,
) -> None:
    from yt_dlp.cookies import YoutubeDLCookieJar

    captured: dict[str, object] = {}
    output = tmp_path / "temporary" / "SAFE_CODE.part"
    jar = SessionCookieProvider().get(
        _CookieContext([_cookie("sessionid", "secret", ".instagram.com")])
    )

    class NativeJarYdl:
        cookiejar = None

        def __init__(self, options: dict[str, object]) -> None:
            self._template = str(options["outtmpl"])
            captured["options"] = options

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def extract_info(self, _url: str, *, download: bool) -> None:
            assert download is True
            captured["jar"] = self.cookiejar
            capture_path = Path(self._template.replace("%(ext)s", "mp4"))
            captured["attempt_directory"] = capture_path.parent
            capture_path.write_bytes(b"fixture-media")

    PythonYtDlpFacade(NativeJarYdl).download(candidate(), jar, output, 100 * 1024 * 1024)
    assert type(captured["jar"]) is YoutubeDLCookieJar
    assert output.read_bytes() == b"fixture-media"
    assert not Path(captured["attempt_directory"]).exists()
    assert list(captured["jar"]) == []
    options = captured["options"]
    assert isinstance(options, dict)
    for key, value in {
        "noplaylist": True,
        "playlistend": 1,
        "merge_output_format": "mp4",
        "keepvideo": False,
        "overwrites": False,
        "nopart": False,
        "continuedl": False,
        "max_filesize": 100 * 1024 * 1024,
        "socket_timeout": 30,
        "retries": 1,
        "fragment_retries": 1,
        "extractor_retries": 1,
        "file_access_retries": 1,
        "sleep_interval": 0.5,
        "max_sleep_interval": 0.5,
        "usenetrc": False,
        "cachedir": False,
    }.items():
        assert options[key] == value
    assert not {"cookiefile", "cookiesfrombrowser", "http_headers"} & set(options)
    for key in (
        "writethumbnail",
        "writeinfojson",
        "writesubtitles",
        "writeautomaticsub",
        "getcomments",
    ):
        assert options[key] is False


def test_fresh_downloader_creates_three_distinct_native_jars(tmp_path: Path) -> None:
    from yt_dlp.cookies import YoutubeDLCookieJar

    captured: list[object] = []

    class NativeJarYdl:
        cookiejar = None

        def __init__(self, options: dict[str, object]) -> None:
            self._template = str(options["outtmpl"])

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def extract_info(self, _url: str, *, download: bool) -> None:
            assert download is True
            captured.append(self.cookiejar)
            Path(self._template.replace("%(ext)s", "mp4")).write_bytes(b"fixture-media")

    downloader = FreshSessionFirstYtDlpDownloader(
        lambda: _CookieContext([_cookie("sessionid", "secret", ".instagram.com")]),
        maximum_bytes=1024,
        facade_factory=lambda: PythonYtDlpFacade(NativeJarYdl),
    )
    for code in ("ONE", "TWO", "THREE"):
        downloader.download(candidate(code), tmp_path / "temporary" / f"{code}.part")
    assert len(captured) == 3
    assert all(type(item) is YoutubeDLCookieJar for item in captured)
    assert len({id(item) for item in captured}) == 3
    assert all(list(item) == [] for item in captured)


def test_attempt_directory_cleanup_does_not_mask_primary_downloader_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "temporary" / "SAFE_CODE.part"
    jar = SessionCookieProvider().get(
        _CookieContext([_cookie("sessionid", "secret", ".instagram.com")])
    )

    class FailingYdl:
        cookiejar = None

        def __init__(self, options: dict[str, object]) -> None:
            self._template = str(options["outtmpl"])

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def extract_info(self, _url: str, *, download: bool) -> None:
            del download
            Path(self._template.replace("%(ext)s", "part")).write_bytes(b"partial")
            raise RuntimeError("signed URL and Cookie: secret")

    monkeypatch.setattr(
        "app.instagram.collector.runtime.downloader.shutil.rmtree",
        lambda _path: (_ for _ in ()).throw(OSError("cleanup failure")),
    )
    facade = PythonYtDlpFacade(FailingYdl)
    with pytest.raises(CollectorRuntimeError) as error:
        facade.download(candidate(), jar, output, 1024)
    assert error.value.code is RuntimeReasonCode.DOWNLOAD_FAILED
    assert facade.last_diagnostics["cleaned_partial_artifacts"] is False


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


@pytest.mark.parametrize("remote", [b"different-size", b"sourcf"])
def test_minio_existing_object_conflict_is_never_overwritten_or_deleted(
    tmp_path: Path, remote: bytes
) -> None:
    workspace = tmp_path / "workspace"
    path = workspace / "temporary" / "SAFE_CODE.part"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"source")
    client = _MemoryMinio()
    key = "instagram-sources/SAFE_CODE.mp4"
    client.objects[key] = remote
    storage = MinioCollectorSourceStorage(client, "offline-reels", workspace, 1024)
    with pytest.raises(CollectorRuntimeError) as error:
        storage.publish(path, key)
    assert error.value.code is RuntimeReasonCode.STORAGE_OBJECT_CONFLICT
    assert client.objects[key] == remote
    assert client.remove_calls == 0


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
    account_id = uuid4()
    profile = settings.profile_root / str(account_id)
    profile.mkdir(parents=True)
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        (profile / name).touch()
    with pytest.raises(CollectorRuntimeError) as error:
        PlaywrightReelsFeed.open(account_id, settings, repository_root=tmp_path / "repository")
    assert error.value.code is RuntimeReasonCode.AUTH_REQUIRED
    assert playwright.launch_options is not None
    assert playwright.launch_options[1]["chromium_sandbox"] is True
    assert playwright.launch_options[1]["viewport"] == {"width": 430, "height": 800}
    assert playwright.launch_options[1]["is_mobile"] is True
    assert playwright.launch_options[1]["has_touch"] is True
    assert "Android 13; Pixel 7" in playwright.launch_options[1]["user_agent"]
    assert playwright.launch_options[1]["args"] == [
        "--window-size=430,800",
        "--window-position=0,0",
        "--force-device-scale-factor=0.9",
        "--kiosk",
    ]
    assert "env" not in playwright.launch_options[1]
    assert context.close_calls == 1
    assert playwright.stop_calls == 1
    assert lock.release_calls == 1
    assert not any((profile / name).exists() for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"))


class _CookieContext:
    def __init__(self, cookies: list[dict[str, object]]) -> None:
        self._cookies = cookies

    def cookies(self) -> list[dict[str, object]]:
        return self._cookies


class _CdpSession:
    def __init__(self, page: FakePage | None = None) -> None:
        self.commands: list[tuple[str, dict[str, object]]] = []
        self.detach_calls = 0
        self._page = page

    def send(self, method: str, parameters: dict[str, object]) -> None:
        self.commands.append((method, parameters))
        if self._page is not None and parameters.get("type") == "touchEnd":
            self._page.complete_input()

    def detach(self) -> None:
        self.detach_calls += 1


class _CdpContext:
    def __init__(self, page: FakePage | None = None) -> None:
        self.session = _CdpSession(page)

    def new_cdp_session(self, _page: FakePage) -> _CdpSession:
        return self.session


class _FakeMouse:
    def __init__(self, page: FakePage) -> None:
        self._page = page
        self.calls: list[tuple[int, int]] = []
        self.moves: list[tuple[float, float]] = []
        self.actions: list[tuple[object, ...]] = []
        self.close_on_wheel = False

    def move(self, x: float, y: float) -> None:
        self.moves.append((x, y))
        self.actions.append(("move", x, y))

    def wheel(self, delta_x: int, delta_y: int) -> None:
        self.calls.append((delta_x, delta_y))
        self.actions.append(("wheel", delta_x, delta_y))
        if self.close_on_wheel:
            self._page.closed = True
            raise RuntimeError("browser closed")
        if self._page._index < len(self._page._candidates) - 1:
            self._page.complete_input()


class _JsonResponse:
    headers = {"content-type": "application/json"}
    url = "https://www.instagram.com/graphql/query/"

    def __init__(self, code: str) -> None:
        self._code = code

    def json(self):
        return {"code": self._code}


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
        self.launch_options = None

        def launch_persistent_context(profile, **options):
            self.launch_options = (profile, options)
            return context

        self.chromium = types.SimpleNamespace(
            launch_persistent_context=launch_persistent_context
        )


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
        self.remove_calls = 0

    def stat_object(self, bucket_name: str, object_name: str):
        del bucket_name
        if object_name not in self.objects:
            raise _MissingObject()
        return types.SimpleNamespace(
            size=len(self.objects[object_name]),
            content_type="video/mp4",
        )

    def get_object(self, bucket_name: str, object_name: str):
        del bucket_name
        return _MemoryResponse(self.objects[object_name])

    def fput_object(self, bucket_name: str, object_name: str, file_path: str, *, content_type: str):
        del bucket_name, content_type
        self.objects[object_name] = Path(file_path).read_bytes()

    def remove_object(self, bucket_name: str, object_name: str):
        del bucket_name
        self.remove_calls += 1
        self.objects.pop(object_name, None)


class _MemoryResponse(BytesIO):
    def release_conn(self) -> None:
        return None


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

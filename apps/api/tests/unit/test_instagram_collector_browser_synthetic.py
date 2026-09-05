# ruff: noqa: E501

from pathlib import Path

import pytest

from app.instagram.collector.runtime.browser_feed import (
    ACTIVE_MEDIA_IDENTITY_PROBE,
    STATE_PROBE,
    PlaywrightReelsFeed,
    TransitionLimits,
)

sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright


def test_local_synthetic_page_selects_central_video_and_confirms_scroll(tmp_path: Path) -> None:
    fixture = tmp_path / "reels.html"
    fixture.write_text(_fixture_html(), encoding="utf-8")
    unexpected_requests: list[str] = []
    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).is_file():
            pytest.skip("local Playwright Chromium is not installed")
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 360, "height": 600})

        def route(route, request):
            if request.url.startswith("http://") or request.url.startswith("https://"):
                unexpected_requests.append(request.url)
                route.abort()
            else:
                route.continue_()

        context.route("**/*", route)
        page = context.new_page()
        page.goto(fixture.as_uri(), wait_until="domcontentloaded")
        feed = PlaywrightReelsFeed(
            page,
            limits=TransitionLimits(polling_seconds=0.01, timeout_seconds=0.5, maximum_scroll_attempts=2),
        )
        assert feed.current().shortcode == "LOCAL_ONE"
        feed.pause_current()
        feed.advance()
        # A local DOM change alone is deliberately insufficient: live
        # collection requires a subsequent authenticated feed-JSON candidate.
        assert feed.wait_for_next("LOCAL_ONE") is None
        feed.close()
        assert unexpected_requests == []
        browser.close()


class _Response:
    headers = {"content-type": "application/json"}

    def __init__(self, code: str) -> None:
        self._code = code

    def json(self):
        return {"code": self._code}


class _TransitionPage:
    def __init__(self) -> None:
        self.closed = False
        self.identities = iter(("NEW_MEDIA", "NEW_MEDIA", "NEW_MEDIA"))
        self._response_handler = None

    def on(self, event, handler) -> None:
        assert event == "response"
        self._response_handler = handler

    def evaluate(self, expression: str):
        if expression == ACTIVE_MEDIA_IDENTITY_PROBE:
            return next(self.identities, "NEW_MEDIA")
        if expression == STATE_PROBE:
            return {"login": False, "checkpoint": False, "limited": False}
        raise AssertionError("unexpected probe")

    def wait_for_timeout(self, timeout: float) -> None:
        del timeout

    def is_closed(self) -> bool:
        return self.closed

    def observe_json(self, code: str) -> None:
        assert self._response_handler is not None
        self._response_handler(_Response(code))


def test_wait_for_next_requires_stable_media_then_post_transition_feed_json() -> None:
    page = _TransitionPage()
    feed = PlaywrightReelsFeed(
        page,
        limits=TransitionLimits(polling_seconds=0.01, timeout_seconds=0.05, maximum_scroll_attempts=2),
    )
    page.observe_json("STALE_1")
    feed._transition_media_identity = "OLD_MEDIA"
    feed._transition_json_checkpoint = feed._feed_json.checkpoint()  # type: ignore[union-attr]

    # The stable different video is seen, but its DOM identity cannot confirm
    # a Reel in isolation.
    assert feed.wait_for_next("OLD_CODE") is None
    assert feed.transition_diagnostics.different_candidate_observed is True
    assert feed.transition_diagnostics.canonical_confirmation_observed is False

    page = _TransitionPage()
    feed = PlaywrightReelsFeed(
        page,
        limits=TransitionLimits(polling_seconds=0.01, timeout_seconds=0.05, maximum_scroll_attempts=2),
    )
    feed._transition_media_identity = "OLD_MEDIA"
    feed._transition_json_checkpoint = feed._feed_json.checkpoint()  # type: ignore[union-attr]
    page.observe_json("CONFIRMED_2")

    confirmed = feed.wait_for_next("OLD_CODE")

    assert confirmed is not None and confirmed.shortcode == "CONFIRMED_2"
    assert feed.transition_diagnostics.stable_sample_count >= 2
    assert feed.transition_diagnostics.canonical_confirmation_observed is True


def _fixture_html() -> str:
    cards = "".join(
        f'<section><a href="https://www.instagram.com/reel/{code}/"><video muted playsinline></video></a></section>'
        for code in ("LOCAL_ONE", "LOCAL_TWO", "LOCAL_THREE")
    )
    return (
        "<!doctype html><html><head><style>"
        "body{margin:0}section,video{height:600px;width:360px;display:block}"
        "</style></head><body>"
        f"{cards}</body></html>"
    )

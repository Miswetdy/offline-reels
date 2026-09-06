# ruff: noqa: E501

from pathlib import Path

import pytest

from app.instagram.collector.runtime.browser_feed import (
    ACTIVE_FEED_INPUT_TARGET_PROBE,
    ACTIVE_MEDIA_IDENTITY_PROBE,
    IDENTITY_PROBE,
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
    url = "https://www.instagram.com/graphql/query/"

    def __init__(self, payload: object) -> None:
        self._payload = payload

    def json(self):
        return self._payload


class _TransitionPage:
    def __init__(self, *, dom_shortcode: str | None = None) -> None:
        self.closed = False
        self.dom_shortcode = dom_shortcode
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
        if expression == IDENTITY_PROBE:
            payload = {
                "video_count": 1,
                "visible_video_count": 1,
                "central_video_present": True,
                "extraction_strategy": "video_anchor",
            }
            if self.dom_shortcode is not None:
                payload["shortcode"] = self.dom_shortcode
                payload["canonical_url"] = f"https://www.instagram.com/reel/{self.dom_shortcode}/"
            return payload
        raise AssertionError("unexpected probe")

    def wait_for_timeout(self, timeout: float) -> None:
        del timeout

    def is_closed(self) -> bool:
        return self.closed

    def observe_json(self, code: str) -> None:
        assert self._response_handler is not None
        self._response_handler(_Response({"code": code}))

    def observe_json_without_code(self) -> None:
        assert self._response_handler is not None
        self._response_handler(_Response({"feed": {"updated": True}}))


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


def test_wait_for_next_uses_current_feed_queue_only_after_media_and_post_action_json() -> None:
    page = _TransitionPage()
    feed = PlaywrightReelsFeed(
        page,
        limits=TransitionLimits(polling_seconds=0.01, timeout_seconds=0.05, maximum_scroll_attempts=2),
    )
    page.observe_json("QUEUED_2")
    feed._transition_media_identity = "OLD_MEDIA"
    feed._transition_json_checkpoint = feed._feed_json.checkpoint()  # type: ignore[union-attr]
    page.observe_json_without_code()

    confirmed = feed.wait_for_next("OLD_CODE")

    assert confirmed is not None and confirmed.shortcode == "QUEUED_2"
    assert feed.transition_diagnostics.stable_media_identity_observed is True
    assert feed.transition_diagnostics.post_action_json_observed is True
    assert feed.transition_diagnostics.canonical_queue_fallback_observed is True


def test_wait_for_next_prefers_different_safe_dom_candidate_after_json_gate() -> None:
    page = _TransitionPage(dom_shortcode="DOM_CONFIRMED_2")
    feed = PlaywrightReelsFeed(
        page,
        limits=TransitionLimits(polling_seconds=0.01, timeout_seconds=0.05, maximum_scroll_attempts=2),
    )
    feed._transition_media_identity = "OLD_MEDIA"
    feed._transition_json_checkpoint = feed._feed_json.checkpoint()  # type: ignore[union-attr]
    page.observe_json_without_code()

    confirmed = feed.wait_for_next("OLD_CODE")

    assert confirmed is not None and confirmed.shortcode == "DOM_CONFIRMED_2"
    assert feed.transition_diagnostics.post_action_json_observed is True
    assert feed.transition_diagnostics.canonical_dom_confirmation_observed is True
    assert feed.transition_diagnostics.canonical_queue_fallback_observed is False


class _TouchSession:
    def __init__(self, page) -> None:
        self.page = page
        self.calls: list[str] = []
        self.detached = False

    def send(self, method: str, params: dict[str, object]) -> None:
        self.calls.append(method)
        if params.get("type") == "touchEnd":
            self.page.observe_json("TOUCH_CONFIRMED")

    def detach(self) -> None:
        self.detached = True


class _TouchContext:
    def __init__(self, page) -> None:
        self.session = _TouchSession(page)

    def new_cdp_session(self, page):
        assert page is self.session.page
        return self.session


class _TouchTransitionPage(_TransitionPage):
    def __init__(self) -> None:
        super().__init__()
        self.identities = iter(("OLD_MEDIA", "NEW_MEDIA", "NEW_MEDIA", "NEW_MEDIA", "NEW_MEDIA"))

    def evaluate(self, expression: str):
        if expression == ACTIVE_FEED_INPUT_TARGET_PROBE:
            return {
                "available": True,
                "in_viewport": True,
                "hit_testable": True,
                "x": 180,
                "start_y": 430,
                "end_y": 120,
            }
        return super().evaluate(expression)


def test_ownerless_hit_testable_central_video_swipe_generates_json_confirmation() -> None:
    page = _TouchTransitionPage()
    context = _TouchContext(page)
    feed = PlaywrightReelsFeed(
        page,
        context=context,
        limits=TransitionLimits(polling_seconds=0.01, timeout_seconds=0.05, maximum_scroll_attempts=2),
    )

    feed.advance()
    confirmed = feed.wait_for_next("OLD_CODE")

    assert context.session.calls == [
        "Input.dispatchTouchEvent",
        "Input.dispatchTouchEvent",
        "Input.dispatchTouchEvent",
    ]
    assert context.session.detached is True
    assert feed.scroll_target_diagnostics.mobile_swipe_performed is True
    assert confirmed is not None and confirmed.shortcode == "TOUCH_CONFIRMED"
    assert feed.transition_diagnostics.stable_media_identity_observed is True
    assert feed.transition_diagnostics.post_action_json_observed is True


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

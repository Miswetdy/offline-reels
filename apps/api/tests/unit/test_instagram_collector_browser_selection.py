"""Local-only selection regressions for central Reel identity extraction."""

from pathlib import Path

import pytest

from app.instagram.collector.runtime.browser_feed import (
    IDENTITY_PROBE,
    PAUSE_PROBE,
    SCROLL_TARGET_PROBE,
    STATE_PROBE,
    PlaywrightReelsFeed,
    TransitionLimits,
)
from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode

sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright


def test_central_video_wins_over_preloaded_neighbour_and_anchor_strategies(tmp_path: Path) -> None:
    fixture = tmp_path / "selection.html"
    fixture.write_text(_selection_html(), encoding="utf-8")
    unexpected: list[str] = []
    with sync_playwright() as playwright:
        browser = _launch_local_chromium_or_skip(playwright)
        context = browser.new_context(viewport={"width": 360, "height": 600})
        context.route("**/*", lambda route: _abort_http(route, unexpected))
        page = context.new_page()
        page.goto(fixture.as_uri(), wait_until="domcontentloaded")
        page.evaluate("window.scrollTo(0, 600)")
        feed = PlaywrightReelsFeed(
            page,
            limits=TransitionLimits(0.01, 0.1, 2),
        )
        current = feed.current()
        assert current.shortcode == "CENTRAL_CONTAINER"
        assert feed.diagnostics["extraction_strategy"] in {
            "ancestor_descendant_anchor",
            "sibling_anchor",
            "sibling_container_anchor",
        }
        assert unexpected == []
        browser.close()


def test_anchor_parent_video_and_absent_identity_have_safe_outcomes(tmp_path: Path) -> None:
    fixture = tmp_path / "anchors.html"
    fixture.write_text(_parent_anchor_html(), encoding="utf-8")
    with sync_playwright() as playwright:
        browser = _launch_local_chromium_or_skip(playwright)
        page = browser.new_page(viewport={"width": 360, "height": 600})
        page.goto(fixture.as_uri(), wait_until="domcontentloaded")
        feed = PlaywrightReelsFeed(page, limits=TransitionLimits(0.01, 0.1, 2))
        assert feed.current().shortcode == "PARENT_ANCHOR"
        assert feed.diagnostics["extraction_strategy"] in {"ancestor_anchor", "closest_anchor"}
        page.set_content('<style>video{width:360px;height:600px}</style><video></video>')
        with pytest.raises(CollectorRuntimeError) as error:
            feed.current()
        assert error.value.code is RuntimeReasonCode.ACTIVE_REEL_NOT_FOUND
        diagnostics = feed.diagnostics
        assert diagnostics["video_count"] == 1
        assert diagnostics["visible_video_count"] == 1
        assert diagnostics["central_video_present"] is True
        assert diagnostics["reason_code"] == "ACTIVE_REEL_NOT_FOUND"
        assert "url" not in diagnostics and "html" not in diagnostics
        browser.close()


class _Page:
    def __init__(
        self,
        *,
        url: str,
        payload: dict[str, object],
        state: dict[str, bool] | None = None,
    ) -> None:
        self.url = url
        self.payload = payload
        self.state = state or {"login": False, "checkpoint": False, "limited": False}
        self.closed = False
        self.pause_calls = 0
        self.mouse = _Mouse()

    def evaluate(self, expression: str):
        if expression == IDENTITY_PROBE:
            return self.payload
        if expression == STATE_PROBE:
            return self.state
        if expression == PAUSE_PROBE:
            self.pause_calls += 1
            return True
        if expression == SCROLL_TARGET_PROBE:
            return {
                "available": True,
                "in_viewport": True,
                "x": 100,
                "y": 200,
                "width": 360,
                "height": 600,
            }
        raise AssertionError("unexpected probe")

    def wait_for_timeout(self, timeout: float) -> None:
        del timeout

    def is_closed(self) -> bool:
        return self.closed


class _Context:
    def __init__(self, pages) -> None:
        self.pages = pages


class _DelayedReelPage(_Page):
    def __init__(self) -> None:
        super().__init__(
            url="https://www.instagram.com/reels/",
            payload={
                "video_count": 0,
                "visible_video_count": 0,
                "central_video_present": False,
                "extraction_strategy": "none",
            },
        )
        self.wait_calls = 0

    def wait_for_timeout(self, timeout: float) -> None:
        del timeout
        self.wait_calls += 1
        self.payload = _payload("ASYNC_READY")


class _Mouse:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []
        self.moves: list[tuple[float, float]] = []

    def move(self, x: float, y: float) -> None:
        self.moves.append((x, y))

    def wheel(self, delta_x: int, delta_y: int) -> None:
        self.calls.append((delta_x, delta_y))


def _payload(code: str | None, *, strategy: str = "closest_anchor") -> dict[str, object]:
    payload: dict[str, object] = {
        "video_count": 2,
        "visible_video_count": 2,
        "central_video_present": True,
        "extraction_strategy": strategy,
    }
    if code is not None:
        payload["shortcode"] = code
        payload["canonical_url"] = f"https://www.instagram.com/reel/{code}/"
    return payload


@pytest.mark.parametrize(
    ("state", "classification"),
    [
        ({"login": True, "checkpoint": False, "limited": False}, "login"),
        ({"login": False, "checkpoint": True, "limited": False}, "challenge"),
    ],
)
def test_context_selects_second_reels_tab_over_login_challenge_or_external_tab(
    state: dict[str, bool], classification: str
) -> None:
    first = _Page(
        url="https://www.instagram.com/accounts/login/",
        payload=_payload(None),
        state=state,
    )
    external = _Page(url="https://example.invalid/reel/OUTSIDE/", payload=_payload("OUTSIDE"))
    reels = _Page(url="https://www.instagram.com/reels/", payload=_payload("SECOND_TAB"))
    feed = PlaywrightReelsFeed(
        first,
        limits=TransitionLimits(0.01, 0.1, 2),
        context=_Context([first, external, reels]),
    )
    assert feed.current().shortcode == "SECOND_TAB"
    feed.pause_current()
    assert reels.pause_calls == 1
    assert first.pause_calls == 0
    feed.advance()
    assert reels.mouse.moves == [(100.0, 200.0)]
    assert reels.mouse.calls == [(0, 540)]
    assert first.mouse.moves == []
    assert external.mouse.moves == []
    assert first.mouse.calls == []
    assert external.mouse.calls == []
    diagnostics = feed.diagnostics
    assert diagnostics["open_page_count"] == 3
    assert diagnostics["page_classifications"] == {
        "reels": 1,
        "login": int(classification == "login"),
        "challenge": int(classification == "challenge"),
        "other": 1,
    }


@pytest.mark.parametrize("path", ["/reel/PATH_ONE/", "/reels/PATH_TWO/"])
def test_pathname_fallback_is_normalized_from_selected_instagram_page(path: str) -> None:
    code = path.split("/")[2]
    page = _Page(
        url=f"https://www.instagram.com{path}",
        payload={
            "video_count": 1,
            "visible_video_count": 1,
            "central_video_present": True,
            "extraction_strategy": "pathname_fallback",
            "shortcode": code,
            "canonical_url": f"https://www.instagram.com/reel/{code}/",
        },
    )
    feed = PlaywrightReelsFeed(
        page,
        limits=TransitionLimits(0.01, 0.1, 2),
        context=_Context([page]),
    )
    candidate = feed.current()
    assert candidate.shortcode == code
    assert candidate.canonical_url == f"https://www.instagram.com/reel/{code}/"


def test_context_waits_for_async_initial_reel_without_scrolling() -> None:
    page = _DelayedReelPage()
    feed = PlaywrightReelsFeed(
        page,
        limits=TransitionLimits(0.01, 0.1, 2),
        context=_Context([page]),
    )

    assert feed.current().shortcode == "ASYNC_READY"
    assert page.wait_calls == 1
    assert page.mouse.moves == []
    assert page.mouse.calls == []


def _abort_http(route, unexpected: list[str]) -> None:
    request_url = route.request.url
    if request_url.startswith(("http://", "https://")):
        unexpected.append(request_url)
        route.abort()
    else:
        route.continue_()


def _launch_local_chromium_or_skip(playwright):
    if not Path(playwright.chromium.executable_path).is_file():
        pytest.skip("local Playwright Chromium is not installed")
    return playwright.chromium.launch(headless=True)


def _selection_html() -> str:
    return """<!doctype html><style>
      body{margin:0}.card{height:600px;width:360px;position:relative}
      .card video{height:600px;width:360px;display:block}
      .prefetch{position:absolute;top:0;left:0;width:1px;height:1px}
    </style>
    <section class="card"><a href="https://www.instagram.com/reel/FIRST/"><video></video></a></section>
    <section class="card"><div><video></video>
    <a href="https://www.instagram.com/reel/CENTRAL_CONTAINER/" class="prefetch"></a></div>
    <a href="https://www.instagram.com/reel/PRELOADED_NEIGHBOUR/" class="prefetch"></a></section>
    <section class="card"><a href="https://www.instagram.com/reel/THIRD/"><video></video></a></section>"""


def _parent_anchor_html() -> str:
    return """<!doctype html><style>video{width:360px;height:600px;display:block}</style>
    <a href="https://www.instagram.com/reel/PARENT_ANCHOR/"><video></video></a>"""

# ruff: noqa: E501

from pathlib import Path

import pytest

from app.instagram.collector.runtime.browser_feed import PlaywrightReelsFeed, TransitionLimits

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
        assert feed.wait_for_next("LOCAL_ONE").shortcode == "LOCAL_TWO"  # type: ignore[union-attr]
        feed.close()
        assert unexpected_requests == []
        browser.close()


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

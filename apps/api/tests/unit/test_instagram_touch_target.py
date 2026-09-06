"""Execute the actual probes, plus regression coverage for fallback diagnostics."""

from dataclasses import asdict

import pytest
from test_instagram_collector_runtime import FakePage, _CdpContext, candidate

from app.instagram.collector.contracts import ScrollTargetDiagnostics
from app.instagram.collector.runtime.browser_feed import (
    ACTIVE_FEED_INPUT_TARGET_PROBE,
    ACTIVE_MEDIA_IDENTITY_PROBE,
    PlaywrightReelsFeed,
    TransitionLimits,
)


@pytest.fixture
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        # Use the installed full Chromium, not a separate headless-shell artifact.
        browser = playwright.chromium.launch(
            executable_path=playwright.chromium.executable_path,
            headless=True,
            chromium_sandbox=True,
        )
        page = browser.new_page(viewport={"width": 430, "height": 800})
        page.route("**/*", lambda route: route.abort())
        yield page
        browser.close()


def test_identity_and_target_select_same_video_with_partial_neighbour(page):
    page.set_content('''<style>
      html,body{margin:0;overflow:hidden}video{position:fixed}
      #central{left:0;top:0;width:430px;height:780px}
      #neighbour{left:400px;top:0;width:430px;height:800px}
    </style><video id="central"></video><video id="neighbour"></video>''')
    page.evaluate(ACTIVE_MEDIA_IDENTITY_PROBE)
    target = page.evaluate(ACTIVE_FEED_INPUT_TARGET_PROBE)
    assert target["hit_testable"] is True
    # Identity must have assigned an ID to the very same hit-tested element.
    assert page.evaluate('''(p) => {
      const video = document.elementFromPoint(p.x, p.start_y);
      return window.__offlineReelsCollectorMediaIds.has(video);
    }''', target)


def test_ownerless_video_and_overlay_endpoints(page):
    page.set_content('''<style>html,body{margin:0;overflow:hidden}
    video{position:fixed;inset:0;width:430px;height:800px}
    </style><video></video>''')
    assert page.evaluate(ACTIVE_FEED_INPUT_TARGET_PROBE)["hit_testable"] is True
    page.evaluate('''() => {
      const overlay = document.createElement('button');
      overlay.style = 'position:fixed;inset:0;z-index:2';
      document.body.append(overlay);
    }''')
    target = page.evaluate(ACTIVE_FEED_INPUT_TARGET_PROBE)
    assert target["available"] is True
    assert target["hit_testable"] is False


def test_wheel_preserves_touch_evidence():
    adapter = PlaywrightReelsFeed(FakePage([candidate()]), limits=TransitionLimits(.01, .03, 2))
    adapter._scroll_target_diagnostics = ScrollTargetDiagnostics(
        active_feed_target_available=True,
        active_feed_target_in_viewport=True,
        active_feed_target_hit_testable=True,
        mobile_swipe_performed=True,
    )
    adapter._pointer_wheel_advance()
    result = asdict(adapter.scroll_target_diagnostics)
    assert result["mobile_swipe_performed"] is True
    assert result["active_feed_target_hit_testable"] is True
    assert result["mouse_move_performed"] is True


@pytest.mark.parametrize("outcome", ["exception", "malformed", "missing", "overlay"])
def test_probe_outcome_survives_wheel_and_engine_merge(outcome):
    from app.instagram.collector.service import CollectorEngine

    class ProbePage(FakePage):
        def evaluate(self, expression):
            if expression == ACTIVE_FEED_INPUT_TARGET_PROBE:
                if outcome == "exception":
                    raise RuntimeError("unsafe browser content must not escape")
                if outcome == "malformed":
                    return "unsafe payload"
                if outcome == "missing":
                    return {"available": False}
                return {"available": True, "in_viewport": True, "hit_testable": False}
            return super().evaluate(expression)

    adapter = PlaywrightReelsFeed(ProbePage([candidate()]), limits=TransitionLimits(.01, .03, 2))
    adapter.advance()
    evidence = asdict(adapter.scroll_target_diagnostics)
    assert evidence["active_feed_probe_attempted"]
    assert evidence["active_feed_probe_failed"] == (outcome in {"exception", "malformed"})
    assert evidence["active_feed_probe_evaluated"] == (outcome in {"missing", "overlay"})
    assert evidence["active_feed_central_video_missing"] == (outcome == "missing")
    assert evidence["active_feed_target_available"] == (outcome == "overlay")
    assert evidence["mouse_move_performed"]
    assert not evidence["mobile_swipe_performed"]
    assert all(type(value) is bool for value in evidence.values())
    engine = object.__new__(CollectorEngine)
    engine._feed = adapter
    merged = dict.fromkeys(evidence, False)
    engine._merge_scroll_target(merged)
    assert merged == evidence


def test_probe_executes_with_no_visible_media(page):
    page.set_content('<video style="display:none"></video>')
    adapter = PlaywrightReelsFeed(page, limits=TransitionLimits(.01, .03, 2))
    assert page.evaluate(ACTIVE_MEDIA_IDENTITY_PROBE) is None
    assert adapter._active_feed_input_target() is None
    assert adapter.scroll_target_diagnostics.active_feed_probe_evaluated
    assert adapter.scroll_target_diagnostics.active_feed_central_video_missing
    assert not adapter.scroll_target_diagnostics.active_feed_probe_failed


def test_sent_touch_is_retained_when_no_media_change_triggers_wheel(monkeypatch):
    page = FakePage([candidate()], scroll_container=True)
    context = _CdpContext(page)
    adapter = PlaywrightReelsFeed(page, context=context, limits=TransitionLimits(.01, .03, 2))
    monkeypatch.setattr(adapter, "_wait_for_media_transition", lambda *args, **kwargs: False)
    adapter.advance()
    assert len(context.session.commands) == 3
    assert page.mouse.calls == [(0, 540)]
    assert adapter.scroll_target_diagnostics.mobile_swipe_performed
    assert adapter.scroll_target_diagnostics.active_feed_probe_evaluated
    assert adapter.scroll_target_diagnostics.active_feed_target_hit_testable

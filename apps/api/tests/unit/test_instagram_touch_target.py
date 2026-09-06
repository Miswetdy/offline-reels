"""Execute the actual probes, plus regression coverage for fallback diagnostics."""

from dataclasses import asdict

import pytest
from test_instagram_collector_runtime import FakePage, _CdpContext, candidate

from app.instagram.collector.contracts import HIT_TEST_DIAGNOSTIC_FLAGS, ScrollTargetDiagnostics
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


@pytest.mark.parametrize(("obstacle", "flag"), [
    ("button", "hit_test_miss_control"),
    ("div", "hit_test_miss_other_element"),
    ("video", "hit_test_miss_other_video"),
    ("pointer-none", "hit_test_miss_video_ancestor"),
    ("null", "hit_test_miss_null"),
])
def test_actual_probe_classifies_blocker_without_exposing_dom(page, obstacle, flag):
    page.set_content('''<style>html,body{margin:0;overflow:hidden}
      #holder{position:fixed;inset:0}video{width:430px;height:800px}
      </style><div id="holder"><video></video></div>''')
    if obstacle == "pointer-none":
        page.evaluate("document.querySelector('video').style.pointerEvents = 'none'")
    elif obstacle == "null":
        page.evaluate("document.elementFromPoint = () => null")
    else:
        page.evaluate('''tag => {
          const overlay = document.createElement(tag);
          overlay.id = 'PRIVATE_DOM_MARKER';
          overlay.style = 'position:fixed;inset:0;width:430px;height:800px;z-index:10';
          document.body.append(overlay);
        }''', obstacle)
    adapter = PlaywrightReelsFeed(page, limits=TransitionLimits(.01, .03, 2))
    assert adapter._active_feed_input_target() is None
    adapter._pointer_wheel_advance()
    evidence = asdict(adapter.scroll_target_diagnostics)
    assert evidence[flag]
    assert evidence["hit_test_video_pointer_events_none"] == (obstacle == "pointer-none")
    assert not evidence["mobile_swipe_performed"]
    assert not evidence["active_feed_target_hit_testable"]
    assert "PRIVATE_DOM_MARKER" not in str(evidence)
    assert all(type(value) is bool for value in evidence.values())


@pytest.mark.parametrize("blocked_half", ["start", "end"])
def test_both_endpoints_sampled_even_when_start_blocked(page, blocked_half):
    page.set_content('''<style>html,body{margin:0;overflow:hidden}
      video{position:fixed;inset:0;width:430px;height:800px}
      button{position:fixed;left:0;width:430px;height:400px;z-index:10}
      </style><video></video><button></button>''')
    page.evaluate(
        "y => document.querySelector('button').style.top = y",
        "400px" if blocked_half == "start" else "0px",
    )
    target = page.evaluate(ACTIVE_FEED_INPUT_TARGET_PROBE)
    assert not target["hit_testable"]
    assert target["hit_test_miss_control"]
    assert target["hit_test_start_video_observed"] == (blocked_half == "end")
    assert target["hit_test_end_video_observed"] == (blocked_half == "start")


def test_hit_test_payload_allowlist_and_engine_merge():
    from app.instagram.collector.service import CollectorEngine

    class PayloadPage(FakePage):
        def evaluate(self, expression):
            if expression == ACTIVE_FEED_INPUT_TARGET_PROBE:
                return {"available": True, "in_viewport": True, "hit_testable": False,
                        "hit_test_miss_control": True, "hit_test_miss_null": "private",
                        "raw_dom": "private"}
            return super().evaluate(expression)

    adapter = PlaywrightReelsFeed(PayloadPage([candidate()]), limits=TransitionLimits(.01, .03, 2))
    adapter.advance()
    engine = object.__new__(CollectorEngine)
    engine._feed = adapter
    evidence = dict.fromkeys(asdict(adapter.scroll_target_diagnostics), False)
    engine._merge_scroll_target(evidence)
    assert evidence["hit_test_miss_control"]
    assert not evidence["hit_test_miss_null"]
    assert "private" not in str(evidence)
    assert all(type(evidence[key]) is bool for key in HIT_TEST_DIAGNOSTIC_FLAGS)


@pytest.mark.parametrize("scenario", ["self-control", "shared-control", "outside", "small-control"])
def test_obstruction_structure_is_independent_of_control_precedence(page, scenario):
    page.set_content('''<style>
      html,body{margin:0;overflow:hidden}
      #card{position:fixed;inset:0}
      video{width:430px;height:800px}
      #cover{position:absolute;inset:0}
      </style><div id="card"><video></video><div id="cover"></div></div>''')
    page.evaluate('''scenario => {
      const card = document.querySelector('#card'), cover = document.querySelector('#cover');
      if (scenario === 'shared-control') card.setAttribute('role', 'button');
      if (scenario === 'self-control' || scenario === 'small-control') {
        cover.setAttribute('role', 'button');
      }
      if (scenario === 'outside') document.body.append(cover);
      if (scenario === 'small-control') cover.style.top = '400px';
    }''', scenario)
    adapter = PlaywrightReelsFeed(page, limits=TransitionLimits(.01, .03, 2))
    assert adapter._active_feed_input_target() is None
    adapter._pointer_wheel_advance()
    evidence = asdict(adapter.scroll_target_diagnostics)
    assert evidence["hit_test_control_self"] == (scenario in {"self-control", "small-control"})
    assert evidence["hit_test_control_inherited"] == (scenario == "shared-control")
    assert evidence["hit_test_control_contains_video"] == (scenario == "shared-control")
    assert evidence["hit_test_hit_video_sibling"] == (scenario != "outside")
    assert evidence["hit_test_hit_shared_near_ancestor"] == (scenario != "outside")
    assert evidence["hit_test_hit_covers_visible_video"] == (scenario != "small-control")
    assert evidence["hit_test_control_covers_visible_video"] == (
        scenario in {"self-control", "shared-control"}
    )
    assert not evidence["hit_test_hit_contains_video"]
    assert not evidence["mobile_swipe_performed"]
    assert all(type(value) is bool for value in evidence.values())


def test_control_containing_video_reports_both_control_and_structure(page):
    page.set_content('''<style>html,body{margin:0;overflow:hidden}
      div{position:fixed;inset:0}video{width:430px;height:800px;pointer-events:none}
      </style><div role="button"><video></video></div>''')
    result = page.evaluate(ACTIVE_FEED_INPUT_TARGET_PROBE)
    assert not result["hit_testable"]
    assert result["hit_test_miss_control"]
    assert result["hit_test_control_self"]
    assert result["hit_test_hit_contains_video"]
    assert result["hit_test_control_contains_video"]
    assert result["hit_test_hit_covers_visible_video"]


def test_fixed_viewport_overlay_keeps_video_below_in_hit_stack(page):
    page.set_content('''<style>html,body{margin:0;overflow:hidden}
      video{position:fixed;inset:0;width:430px;height:800px}
      button{position:fixed;inset:0;width:430px;height:800px;z-index:2}
      </style><video></video><button></button>''')

    result = page.evaluate(ACTIVE_FEED_INPUT_TARGET_PROBE)

    assert not result["hit_testable"]
    assert result["hit_test_stack_contains_video"]
    assert result["hit_test_stack_video_below_hit"]
    assert result["hit_test_hit_fixed_ancestor"]
    assert result["hit_test_hit_covers_viewport"]
    assert result["hit_test_endpoint_inside_visual_viewport"]


def test_external_hit_without_video_in_stack_distinguishes_coordinate_evidence(page):
    page.set_content('''<style>html,body{margin:0;overflow:hidden}
      video{position:fixed;inset:0;width:430px;height:800px}
      </style><video></video><button id="outside"></button>''')
    page.evaluate('''() => {
      const outside = document.querySelector('#outside');
      document.elementFromPoint = () => outside;
      document.elementsFromPoint = () => [outside];
    }''')

    result = page.evaluate(ACTIVE_FEED_INPUT_TARGET_PROBE)

    assert not result["hit_testable"]
    assert not result["hit_test_stack_contains_video"]
    assert not result["hit_test_stack_video_below_hit"]
    assert result["hit_test_endpoint_inside_visual_viewport"]
    assert result["hit_test_visual_viewport_present"]


def test_other_visible_video_layer_relation_is_reported_without_targeting_it(page):
    page.set_content('''<style>html,body{margin:0;overflow:hidden}
      #selected{position:fixed;inset:0;width:430px;height:800px}
      #other-card{position:fixed;left:400px;top:0;width:430px;height:800px}
      #other{width:430px;height:800px}.layer{position:fixed;inset:0;z-index:2}
      </style><video id="selected"></video><div id="other-card"><video id="other"></video>
      <button class="layer"></button></div>''')

    result = page.evaluate(ACTIVE_FEED_INPUT_TARGET_PROBE)

    assert not result["hit_testable"]
    assert result["hit_test_hit_shared_near_ancestor_other_video"]
    assert result["hit_test_hit_has_other_video_relation"]
    assert not result["hit_test_hit_no_visible_video_relation"]


def test_page_shell_layer_has_no_visible_video_relation(page):
    page.set_content('''<style>html,body{margin:0;overflow:hidden}
      video{position:fixed;inset:0;width:430px;height:800px}
      main{position:fixed;inset:0}.layer{position:absolute;inset:0}
      </style><video></video><main><button class="layer"></button></main>''')

    result = page.evaluate(ACTIVE_FEED_INPUT_TARGET_PROBE)

    assert not result["hit_testable"]
    assert result["hit_test_hit_shell_semantic_ancestor"]
    assert result["hit_test_hit_no_visible_video_relation"]
    assert not result["hit_test_hit_has_other_video_relation"]


def test_noninteractive_main_shell_is_a_narrowly_allowed_swipe_surface(page):
    page.set_content('''<style>html,body{margin:0;overflow:hidden}
      video,main{position:fixed;inset:0;width:430px;height:800px}
      main{z-index:2}</style><video></video><main></main>''')

    result = page.evaluate(ACTIVE_FEED_INPUT_TARGET_PROBE)

    assert result["hit_testable"]
    assert result["hit_test_hit_is_shell_surface"]
    assert result["hit_test_shell_surface_eligible"]
    assert result["hit_test_stack_contains_video"]
    assert result["hit_test_stack_video_below_hit"]
    assert not result["hit_test_miss_control"]


@pytest.mark.parametrize("attributes", ['role="button"', 'aria-hidden="true"', 'inert'])
def test_interactive_or_hidden_main_shell_is_never_a_swipe_surface(page, attributes):
    page.set_content(f'''<style>html,body{{margin:0;overflow:hidden}}
      video,main{{position:fixed;inset:0;width:430px;height:800px}}
      main{{z-index:2}}</style><video></video><main {attributes}></main>''')

    result = page.evaluate(ACTIVE_FEED_INPUT_TARGET_PROBE)

    assert not result["hit_test_shell_surface_eligible"]
    # An inert element is removed from hit-testing, so the direct video path
    # may legitimately become available again.  The shell branch itself must
    # never admit it.
    if result["hit_testable"]:
        assert result["hit_test_start_video_observed"]
        assert result["hit_test_end_video_observed"]


@pytest.mark.parametrize(
    ("overlay", "expected"),
    [
        (
            '<button class="layer" disabled></button>',
            {
                "hit_test_control_native_button",
                "hit_test_control_disabled",
                "hit_test_control_focusable",
            },
        ),
        (
            (
                '<div role="dialog" aria-modal="true"><div class="layer" '
                'role="button" aria-disabled="true" tabindex="0"></div></div>'
            ),
            {
                "hit_test_control_role_button",
                "hit_test_control_aria_disabled",
                "hit_test_control_focusable",
                "hit_test_control_modal_or_dialog_ancestor",
            },
        ),
        (
            '<a class="layer" href="#" style="touch-action:none"></a>',
            {
                "hit_test_control_anchor",
                "hit_test_control_focusable",
                "hit_test_control_touch_action_none",
            },
        ),
    ],
)
def test_local_interactive_blocker_reports_only_safe_role_and_state_flags(page, overlay, expected):
    page.set_content(f'''<style>html,body{{margin:0;overflow:hidden}}
      video{{position:fixed;inset:0;width:430px;height:800px}}
      .layer{{position:fixed;inset:0;z-index:2}}</style><video></video>{overlay}''')

    result = page.evaluate(ACTIVE_FEED_INPUT_TARGET_PROBE)

    assert not result["hit_testable"]
    assert result["hit_test_miss_control"]
    assert all(result[flag] for flag in expected)
    assert all(type(result[flag]) is bool for flag in HIT_TEST_DIAGNOSTIC_FLAGS)

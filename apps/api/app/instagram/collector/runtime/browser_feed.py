"""Bounded Playwright Reels feed adapter; no network observation or page dumps."""

# ruff: noqa: E501  # Embedded JavaScript probes retain readable browser syntax.

import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse
from uuid import UUID

from app.instagram.collector.canonical import InvalidReelCandidate, validate_candidate
from app.instagram.collector.contracts import (
    HIT_TEST_DIAGNOSTIC_FLAGS,
    ReelCandidate,
    ScrollTargetDiagnostics,
    TransitionSamplingDiagnostics,
)
from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode
from app.instagram.collector.runtime.feed_json import FeedJsonCandidateCatalog
from app.instagram.collector.runtime.profile_lock import ProfileLock, profile_path
from app.instagram.collector.runtime.settings import CollectorRuntimeSettings

MOBILE_INSTAGRAM_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36"
)

IDENTITY_PROBE = """
() => {
  const validPath = (pathname) => /^\\/reels?\\/([A-Za-z0-9_-]{1,64})\\/$/.exec(pathname || '');
  const viewport = { width: window.innerWidth, height: window.innerHeight };
  const midpoint = { x: viewport.width / 2, y: viewport.height / 2 };
  const allVideos = [...document.querySelectorAll('video')];
  const visible = allVideos.map((video) => {
    const rect = video.getBoundingClientRect();
    const width = Math.max(0, Math.min(rect.right, viewport.width) - Math.max(rect.left, 0));
    const height = Math.max(0, Math.min(rect.bottom, viewport.height) - Math.max(rect.top, 0));
    const area = width * height;
    return { video, rect, area, distance: Math.hypot((rect.left + rect.right) / 2 - midpoint.x, (rect.top + rect.bottom) / 2 - midpoint.y) };
  }).filter((item) => item.area > 0).sort((left, right) => left.distance - right.distance);
  const result = { video_count: allVideos.length, visible_video_count: visible.length, central_video_present: visible.length > 0, extraction_strategy: 'none' };
  if (!visible.length) return result;
  const selected = visible[0];
  const anchors = [];
  const addAnchor = (anchor, strategy) => {
    if (!(anchor instanceof HTMLAnchorElement) || anchors.some((item) => item.anchor === anchor)) return;
    let parsed;
    try { parsed = new URL(anchor.getAttribute('href') || '', location.href); } catch { return; }
    if (parsed.hostname && parsed.hostname !== 'www.instagram.com') return;
    const match = validPath(parsed.pathname);
    if (!match) return;
    anchors.push({ anchor, strategy, shortcode: match[1] });
  };
  let node = selected.video;
  for (let depth = 0; depth < 10 && node; depth += 1) {
    if (node instanceof HTMLAnchorElement) addAnchor(node, depth === 0 ? 'video_anchor' : 'ancestor_anchor');
    node = node.parentElement;
  }
  addAnchor(selected.video.closest('a[href]'), 'closest_anchor');
  node = selected.video.parentElement;
  for (let depth = 0; depth < 8 && node; depth += 1) {
    if (node === document.body || node === document.documentElement) break;
    for (const anchor of node.querySelectorAll(':scope a[href]')) addAnchor(anchor, 'ancestor_descendant_anchor');
    for (const sibling of node.parentElement ? [...node.parentElement.children] : []) {
      if (sibling === node) continue;
      if (sibling instanceof HTMLAnchorElement) addAnchor(sibling, 'sibling_anchor');
      for (const anchor of sibling.querySelectorAll?.('a[href]') || []) addAnchor(anchor, 'sibling_container_anchor');
    }
    node = node.parentElement;
  }
  const matching = anchors.map((item) => {
    const rect = item.anchor.getBoundingClientRect();
    const overlap = Math.max(0, Math.min(rect.right, selected.rect.right) - Math.max(rect.left, selected.rect.left)) * Math.max(0, Math.min(rect.bottom, selected.rect.bottom) - Math.max(rect.top, selected.rect.top));
    const distance = Math.hypot((rect.left + rect.right) / 2 - (selected.rect.left + selected.rect.right) / 2, (rect.top + rect.bottom) / 2 - (selected.rect.top + selected.rect.bottom) / 2);
    return { ...item, overlap, distance };
  }).filter((item) => item.overlap > 0 || ['video_anchor', 'ancestor_anchor', 'closest_anchor'].includes(item.strategy))
    .sort((left, right) => right.overlap - left.overlap || left.distance - right.distance);
  if (matching.length) {
    result.shortcode = matching[0].shortcode;
    result.canonical_url = `https://www.instagram.com/reel/${matching[0].shortcode}/`;
    result.extraction_strategy = matching[0].strategy;
    return result;
  }
  const fallback = validPath(location.pathname);
  if (location.protocol === 'https:' && location.hostname === 'www.instagram.com' && fallback) {
    result.shortcode = fallback[1];
    result.canonical_url = `https://www.instagram.com/reel/${fallback[1]}/`;
    result.extraction_strategy = 'pathname_fallback';
  }
  return result;
}
"""

# Aggregate-only troubleshooting probe. It never returns attributes, hrefs,
# DOM text, URLs, cookie data, or media sources.
IDENTITY_STRUCTURE_PROBE = """
() => {
  const validPath = (pathname) => /^\\/reels?\\/([A-Za-z0-9_-]{1,64})\\/$/.test(pathname || '');
  const viewport = { width: window.innerWidth, height: window.innerHeight };
  const videos = [...document.querySelectorAll('video')].map((video) => {
    const rect = video.getBoundingClientRect();
    const width = Math.max(0, Math.min(rect.right, viewport.width) - Math.max(rect.left, 0));
    const height = Math.max(0, Math.min(rect.bottom, viewport.height) - Math.max(rect.top, 0));
    return { video, area: width * height };
  });
  const visible = videos.filter((item) => item.area > 0);
  const reelAnchor = (anchor) => {
    try {
      const parsed = new URL(anchor.getAttribute('href') || '', location.href);
      return parsed.hostname === 'www.instagram.com' && validPath(parsed.pathname);
    } catch { return false; }
  };
  const pageReelAnchorCount = [...document.querySelectorAll('a[href]')].filter(reelAnchor).length;
  let nearbyReelAnchorCount = 0;
  let ancestorDataAttributeCount = 0;
  if (visible.length) {
    let node = visible[0].video;
    for (let depth = 0; depth < 8 && node; depth += 1) {
      ancestorDataAttributeCount += node.getAttributeNames().filter((name) => name.startsWith('data-')).length;
      nearbyReelAnchorCount += [...node.querySelectorAll?.('a[href]') || []].filter(reelAnchor).length;
      node = node.parentElement;
    }
  }
  return {
    video_count: videos.length,
    visible_video_count: visible.length,
    central_video_present: visible.length > 0,
    page_reel_anchor_count: pageReelAnchorCount,
    nearby_reel_anchor_count: nearbyReelAnchorCount,
    ancestor_data_attribute_count: ancestorDataAttributeCount,
    location_is_specific_reel: validPath(location.pathname),
  };
}
"""

PAUSE_PROBE = """
() => {
  const midpoint = window.innerHeight / 2;
  const videos = [...document.querySelectorAll('video')].map((video) => ({ video, rect: video.getBoundingClientRect() }))
    .filter(({ rect }) => Math.max(0, Math.min(rect.bottom, window.innerHeight) - Math.max(rect.top, 0)) > 0)
    .sort((left, right) => Math.abs((left.rect.top + left.rect.bottom) / 2 - midpoint) - Math.abs((right.rect.top + right.rect.bottom) / 2 - midpoint));
  if (!videos.length) return false;
  videos[0].video.pause();
  return true;
}
"""

_CENTRAL_MEDIA_SELECTION = """
  const width = innerWidth, height = innerHeight;
  const visible = [...document.querySelectorAll('video')].map((video) => {
    const rect = video.getBoundingClientRect();
    const left = Math.max(0, rect.left), right = Math.min(width, rect.right);
    const top = Math.max(0, rect.top), bottom = Math.min(height, rect.bottom);
    const style = getComputedStyle(video);
    const area = style.visibility === 'hidden' || style.visibility === 'collapse' || style.display === 'none' || Number(style.opacity) === 0
      ? 0 : Math.max(0, right - left) * Math.max(0, bottom - top);
    const distance = Math.hypot((rect.left + rect.right) / 2 - width / 2, (rect.top + rect.bottom) / 2 - height / 2);
    return { video, left, right, top, bottom, area, distance };
  }).filter((item) => item.area > 0).sort((a, b) => a.distance - b.distance || b.area - a.area);
"""

ACTIVE_MEDIA_IDENTITY_PROBE = "() => {" + _CENTRAL_MEDIA_SELECTION + """
  if (!visible.length) return null;
  // Collector pauses the current Reel while its separate downloader runs.
  // Restore muted playback before testing an input transition; this is the
  // accepted spike behaviour and lets mobile Instagram activate the next card
  // without exposing sound or retaining media state outside the browser.
  visible[0].video.muted = true;
  visible[0].video.play().catch(() => {});
  const ids = window.__offlineReelsCollectorMediaIds || (window.__offlineReelsCollectorMediaIds = new WeakMap());
  const next = window.__offlineReelsCollectorMediaIdNext || 1;
  if (!ids.has(visible[0].video)) { ids.set(visible[0].video, next); window.__offlineReelsCollectorMediaIdNext = next + 1; }
  return `${ids.get(visible[0].video)}:${visible[0].video.duration || 0}:${visible[0].video.videoWidth}x${visible[0].video.videoHeight}`;
}
"""


SCROLL_TARGET_PROBE = """
() => {
  const width = window.innerWidth;
  const height = window.innerHeight;
  const videos = [...document.querySelectorAll('video')].map((video) => {
    const rect = video.getBoundingClientRect();
    const left = Math.max(0, rect.left);
    const right = Math.min(width, rect.right);
    const top = Math.max(0, rect.top);
    const bottom = Math.min(height, rect.bottom);
    const visibleWidth = Math.max(0, right - left);
    const visibleHeight = Math.max(0, bottom - top);
    const area = visibleWidth * visibleHeight;
    const distance = Math.hypot((left + right) / 2 - width / 2, (top + bottom) / 2 - height / 2);
    return { left, right, top, bottom, area, distance };
  }).filter((item) => item.area > 0).sort((left, right) => left.distance - right.distance);
  if (!videos.length) return { available: false, in_viewport: false };
  const selected = videos[0];
  const x = (selected.left + selected.right) / 2;
  const y = (selected.top + selected.bottom) / 2;
  return { available: true, in_viewport: x >= 0 && x < width && y >= 0 && y < height, x, y, width, height };
}
"""


SCROLL_CONTAINER_PROBE = """
() => {
  const videos = [...document.querySelectorAll('video')];
  if (!videos.length) return false;
  const midpoint = innerHeight / 2;
  const selected = videos
    .map((video) => ({ video, rect: video.getBoundingClientRect() }))
    .filter(({ rect }) => Math.max(0, Math.min(rect.bottom, innerHeight) - Math.max(rect.top, 0)) > 0)
    .sort((left, right) => Math.abs((left.rect.top + left.rect.bottom) / 2 - midpoint) - Math.abs((right.rect.top + right.rect.bottom) / 2 - midpoint))[0];
  if (!selected) return false;
  for (let node = selected.video.parentElement; node && node !== document.documentElement; node = node.parentElement) {
    const style = getComputedStyle(node);
    if (/(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight) {
      node.scrollBy({ top: Math.round(innerHeight * 0.92), behavior: 'instant' });
      return true;
    }
  }
  window.scrollBy({ top: Math.round(innerHeight * 0.92), behavior: 'instant' });
  return true;
}
"""


ACTIVE_FEED_INPUT_TARGET_PROBE = "() => {" + _CENTRAL_MEDIA_SELECTION + """
  if (!visible.length) return { available: false };
  const selected = visible[0];
  let owner = null;
  for (let node = selected.video.parentElement; node && node !== document.documentElement; node = node.parentElement) {
    const style = getComputedStyle(node);
    if (/(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight) { owner = node; break; }
  }
  if (!owner) {
    const root = document.scrollingElement;
    if (root && root.scrollHeight > root.clientHeight) owner = root;
  }
  // A CSS-locked React feed can have no ordinary DOM scroll owner at all.
  // The visible central video itself is then the only permissible gesture
  // surface; never substitute an overlay or script-driven scroll mutation.
  let left = selected.left, right = selected.right, top = selected.top, bottom = selected.bottom;
  if (owner) {
    const rect = owner.getBoundingClientRect();
    left = Math.max(left, Math.max(0, rect.left)); right = Math.min(right, Math.min(width, rect.right));
    top = Math.max(top, Math.max(0, rect.top)); bottom = Math.min(bottom, Math.min(height, rect.bottom));
  }
  if (!(right > left && bottom > top)) return { available: true, in_viewport: false };
  // Both touch endpoints must hit the central video itself. Coordinates stay
  // inside this browser process and never appear in diagnostics or results.
  const xValues = [.32, .5, .68].map((ratio) => left + (right - left) * ratio);
  const yPairs = [[.76, .28], [.68, .22], [.62, .18]];
  const diagnostics = {
    hit_test_start_video_observed: false, hit_test_end_video_observed: false,
    hit_test_miss_null: false, hit_test_miss_control: false,
    hit_test_miss_other_video: false, hit_test_miss_video_ancestor: false,
    hit_test_miss_video_descendant: false, hit_test_miss_other_element: false,
    hit_test_video_pointer_events_none: getComputedStyle(selected.video).pointerEvents === 'none',
    hit_test_video_native_controls: selected.video.controls === true,
    hit_test_control_self: false,
    hit_test_control_inherited: false,
    hit_test_hit_contains_video: false,
    hit_test_hit_inside_video: false,
    hit_test_hit_video_sibling: false,
    hit_test_hit_shared_near_ancestor: false,
    hit_test_hit_covers_visible_video: false,
    hit_test_control_contains_video: false,
    hit_test_control_covers_visible_video: false,
    hit_test_stack_contains_video: false,
    hit_test_stack_video_below_hit: false,
    hit_test_hit_fixed_ancestor: false,
    hit_test_hit_covers_viewport: false,
    hit_test_visual_viewport_present: Boolean(window.visualViewport),
    hit_test_visual_viewport_differs_from_layout: false,
    hit_test_endpoint_inside_visual_viewport: false,
  };
  const visual = window.visualViewport;
  if (visual) {
    diagnostics.hit_test_visual_viewport_differs_from_layout = visual.scale !== 1 || visual.offsetLeft !== 0 || visual.offsetTop !== 0 || Math.abs(visual.width - width) > 1 || Math.abs(visual.height - height) > 1;
  }
  const controls = 'button,a,input,select,textarea,[role="button"],[role="slider"],[contenteditable="true"]';
  const coversVideo = (element) => {
    const r = element.getBoundingClientRect();
    return r.left <= selected.left && r.right >= selected.right && r.top <= selected.top && r.bottom >= selected.bottom;
  };
  const observeStructure = (hit, control) => {
    // Independent facts: control precedence must not hide structural relations.
    diagnostics.hit_test_control_self ||= control === hit;
    diagnostics.hit_test_control_inherited ||= control !== null && control !== hit;
    diagnostics.hit_test_hit_contains_video ||= hit.contains(selected.video);
    diagnostics.hit_test_hit_inside_video ||= selected.video.contains(hit);
    diagnostics.hit_test_hit_video_sibling ||= hit.parentElement === selected.video.parentElement;
    diagnostics.hit_test_hit_covers_visible_video ||= coversVideo(hit);
    for (let node = hit; node && node !== document.body && node !== document.documentElement; node = node.parentElement) {
      if (getComputedStyle(node).position === 'fixed') { diagnostics.hit_test_hit_fixed_ancestor = true; break; }
    }
    const hitRect = hit.getBoundingClientRect();
    diagnostics.hit_test_hit_covers_viewport ||= hitRect.left <= 0 && hitRect.right >= width && hitRect.top <= 0 && hitRect.bottom >= height;
    if (control) {
      diagnostics.hit_test_control_contains_video ||= control.contains(selected.video);
      diagnostics.hit_test_control_covers_visible_video ||= coversVideo(control);
    }
    // A bounded structural hint, not an inferred Instagram card identity.
    let node = selected.video.parentElement;
    for (let depth = 0; depth < 4 && node && node !== document.body && node !== document.documentElement; depth++, node = node.parentElement) {
      if (node.contains(hit)) { diagnostics.hit_test_hit_shared_near_ancestor = true; break; }
    }
  };
  const classify = (hit) => {
    if (hit === selected.video) return true;
    const control = hit ? hit.closest(controls) : null;
    if (hit) observeStructure(hit, control);
    if (!hit) diagnostics.hit_test_miss_null = true;
    else if (control) diagnostics.hit_test_miss_control = true;
    else if (hit instanceof HTMLVideoElement) diagnostics.hit_test_miss_other_video = true;
    else if (hit.contains(selected.video)) diagnostics.hit_test_miss_video_ancestor = true;
    else if (selected.video.contains(hit)) diagnostics.hit_test_miss_video_descendant = true;
    else diagnostics.hit_test_miss_other_element = true;
    return false;
  };
  let gesture = null;
  for (const x of xValues) for (const [startRatio, endRatio] of yPairs) {
    const startY = top + (bottom - top) * startRatio;
    const endY = top + (bottom - top) * endRatio;
    // Independently sample both endpoints, including when the start is blocked.
    const observePoint = (x, y) => {
      if (!visual || (x >= visual.offsetLeft && x < visual.offsetLeft + visual.width && y >= visual.offsetTop && y < visual.offsetTop + visual.height)) diagnostics.hit_test_endpoint_inside_visual_viewport = true;
      const stack = document.elementsFromPoint(x, y);
      const videoIndex = stack.indexOf(selected.video);
      if (videoIndex >= 0) {
        diagnostics.hit_test_stack_contains_video = true;
        if (videoIndex > 0) diagnostics.hit_test_stack_video_below_hit = true;
      }
      return classify(document.elementFromPoint(x, y));
    };
    const startHit = observePoint(x, startY);
    const endHit = observePoint(x, endY);
    diagnostics.hit_test_start_video_observed ||= startHit;
    diagnostics.hit_test_end_video_observed ||= endHit;
    if (startHit && endHit) { gesture = [x, startY, endY]; break; }
  }
  if (!gesture) return { available: true, in_viewport: true, hit_testable: false, ...diagnostics };
  const [x, startY, endY] = gesture;
  return { available: true, in_viewport: true, hit_testable: true, x, start_y: startY, end_y: endY, ...diagnostics };
}
"""

STATE_PROBE = """
() => ({
  login: Boolean(document.querySelector('input[name="username"], input[name="password"]')),
  checkpoint: /checkpoint|challenge/.test(location.pathname) || Boolean(document.querySelector('[data-testid="checkpoint"], [data-testid="challenge"]')),
  limited: Boolean(document.querySelector('[data-testid="temporarily-limited"]')),
})
"""


class BrowserMouse(Protocol):
    def move(self, x: float, y: float) -> None: ...

    def wheel(self, delta_x: float, delta_y: float) -> None: ...


class CdpSession(Protocol):
    def send(self, method: str, params: dict[str, object]) -> object: ...

    def detach(self) -> None: ...


class BrowserPage(Protocol):
    @property
    def url(self) -> str: ...

    @property
    def mouse(self) -> BrowserMouse: ...

    def evaluate(self, expression: str): ...

    def goto(self, url: str, *, wait_until: str): ...

    def wait_for_timeout(self, timeout: float) -> None: ...

    def is_closed(self) -> bool: ...


@dataclass(frozen=True)
class TransitionLimits:
    polling_seconds: float
    timeout_seconds: float
    maximum_scroll_attempts: int
    stabilization_seconds: float = 1.0


class PlaywrightReelsFeed:
    def __init__(
        self,
        page: BrowserPage,
        *,
        limits: TransitionLimits,
        context=None,
        playwright=None,
        profile_lock: ProfileLock | None = None,
    ) -> None:
        self._page = page
        self._limits = limits
        self._context = context
        self._playwright = playwright
        self._profile_lock = profile_lock
        self._scroll_attempts = 0
        self._closed = False
        self._diagnostics = _empty_diagnostics()
        self._transition_diagnostics = TransitionSamplingDiagnostics()
        self._scroll_target_diagnostics = ScrollTargetDiagnostics()
        self._transition_media_identity: str | None = None
        self._transition_media_confirmed = False
        self._transition_json_checkpoint = 0
        self._force_pointer_wheel_next_advance = False
        try:
            self._feed_json = FeedJsonCandidateCatalog(page)
        except Exception:
            self._feed_json = None

    @classmethod
    def open(
        cls,
        account_id: UUID,
        settings: CollectorRuntimeSettings,
        *,
        repository_root: Path,
        allow_login_bootstrap: bool = False,
    ) -> PlaywrightReelsFeed:
        settings.require_live(repository_root=repository_root)
        assert settings.profile_root is not None
        playwright = None
        context = None
        lock: ProfileLock | None = None
        try:
            profile = profile_path(settings.profile_root, account_id)
            lock = ProfileLock(profile)
            lock.acquire()
            _clear_transient_chromium_locks(profile)
            from playwright.sync_api import sync_playwright

            playwright = sync_playwright().start()
            launch_options: dict[str, object] = {
                "headless": settings.headless,
                "chromium_sandbox": True,
                # The shared profile was created by the mobile login browser.
                # Match that supported presentation contract rather than
                # mixing a mobile profile with Playwright's desktop defaults.
                "user_agent": MOBILE_INSTAGRAM_USER_AGENT,
                "viewport": {"width": 430, "height": 800},
                "is_mobile": True,
                "has_touch": True,
            }
            context = playwright.chromium.launch_persistent_context(
                str(profile),
                # Playwright defaults this to false and would otherwise add
                # --no-sandbox. Collector pages are external input, so the
                # Chromium user-namespace sandbox is mandatory on every host.
                **launch_options,
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.instagram.com/reels/", wait_until="domcontentloaded")
            feed = cls(
                page,
                limits=TransitionLimits(
                    settings.transition_polling_seconds,
                    settings.transition_timeout_seconds,
                    settings.maximum_scroll_attempts,
                ),
                context=context,
                playwright=playwright,
                profile_lock=lock,
            )
            if not allow_login_bootstrap:
                feed._raise_if_controlled_stop()
            return feed
        except CollectorRuntimeError:
            _close_runtime(context, playwright, lock)
            raise
        except Exception:
            _close_runtime(context, playwright, lock)
            raise CollectorRuntimeError(RuntimeReasonCode.BROWSER_CLOSED) from None

    @property
    def cookie_context(self):
        if self._context is None or self._closed:
            raise CollectorRuntimeError(RuntimeReasonCode.BROWSER_CLOSED)
        return self._context

    @property
    def diagnostics(self) -> dict[str, object]:
        """Aggregate-only state: deliberately no URL, DOM or account data."""

        return dict(self._diagnostics)

    @property
    def transition_diagnostics(self) -> TransitionSamplingDiagnostics:
        return self._transition_diagnostics

    @property
    def scroll_target_diagnostics(self) -> ScrollTargetDiagnostics:
        return self._scroll_target_diagnostics

    def current(self) -> ReelCandidate:
        if self._closed:
            raise CollectorRuntimeError(RuntimeReasonCode.BROWSER_CLOSED)
        if self._context is not None:
            return self._wait_for_initial_reel()
        self._raise_if_closed()
        self._raise_if_controlled_stop()
        return self._candidate_from_probe()

    def identity_structure_diagnostics(self) -> dict[str, int | bool]:
        """Return safe aggregate identity evidence without content extraction."""
        if self._closed:
            raise CollectorRuntimeError(RuntimeReasonCode.BROWSER_CLOSED)
        polls = max(1, int(self._limits.timeout_seconds / self._limits.polling_seconds))
        result = _empty_identity_structure_diagnostics()
        for attempt in range(polls):
            self._raise_if_closed()
            self._raise_if_controlled_stop()
            result = _identity_structure_from_payload(self._page.evaluate(IDENTITY_STRUCTURE_PROBE))
            if result["central_video_present"]:
                return result
            if attempt + 1 < polls:
                self._page.wait_for_timeout(self._limits.polling_seconds * 1000)
        return result

    def _wait_for_initial_reel(self) -> ReelCandidate:
        """Boundedly wait for the first async-rendered Reel without scrolling."""
        polls = max(1, int(self._limits.timeout_seconds / self._limits.polling_seconds))
        last_error: CollectorRuntimeError | None = None
        for attempt in range(polls):
            self._raise_if_closed()
            try:
                return self._select_reels_page()
            except CollectorRuntimeError as error:
                if error.code is not RuntimeReasonCode.ACTIVE_REEL_NOT_FOUND:
                    raise
                last_error = error
            if attempt + 1 < polls:
                self._page.wait_for_timeout(self._limits.polling_seconds * 1000)
        assert last_error is not None
        raise last_error

    def pause_current(self) -> None:
        self._raise_if_closed()
        if self._page.evaluate(PAUSE_PROBE) is not True:
            self._diagnostics["reason_code"] = RuntimeReasonCode.ACTIVE_REEL_NOT_FOUND.value
            raise CollectorRuntimeError(RuntimeReasonCode.ACTIVE_REEL_NOT_FOUND)

    def advance(self) -> None:
        self._raise_if_closed()
        if self._scroll_attempts >= self._limits.maximum_scroll_attempts:
            raise CollectorRuntimeError(RuntimeReasonCode.TRANSITION_TIMEOUT)
        self._scroll_target_diagnostics = ScrollTargetDiagnostics()
        self._transition_media_identity = self._active_media_identity()
        self._transition_media_confirmed = False
        self._transition_json_checkpoint = (
            self._feed_json.checkpoint() if self._feed_json is not None else 0
        )
        if self._force_pointer_wheel_next_advance:
            # A previous action changed the rendered media element but the
            # authenticated feed catalog never confirmed a new Reel.  Do not
            # repeat that ambiguous action: use the accepted bounded pointer
            # fallback on the one permitted retry.
            self._force_pointer_wheel_next_advance = False
            self._pointer_wheel_advance()
            self._scroll_attempts += 1
            return
        if self._transition_media_identity is not None and self._mobile_feed_swipe_advances(
            self._transition_media_identity
        ):
            self._transition_media_confirmed = True
            self._scroll_attempts += 1
            return
        if self._transition_media_identity is not None and self._keyboard_advances(
            self._transition_media_identity
        ):
            self._transition_media_confirmed = True
            self._scroll_attempts += 1
            return

        self._pointer_wheel_advance()
        self._scroll_attempts += 1

    def _mobile_feed_swipe_advances(self, previous_identity: str) -> bool:
        """Send one native touch swipe to the verified active feed owner."""
        target = self._active_feed_input_target()
        if target is None:
            return False
        x, start_y, end_y = target
        session: CdpSession | None = None
        try:
            create_session = getattr(self._context, "new_cdp_session", None)
            if not callable(create_session):
                return False
            session = create_session(self._page)
            session.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": start_y, "id": 1}]})
            session.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": end_y, "id": 1}]})
            session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            self._scroll_target_diagnostics = replace(
                self._scroll_target_diagnostics,
                active_feed_target_available=True,
                active_feed_target_in_viewport=True,
                active_feed_target_hit_testable=True,
                mobile_swipe_performed=True,
            )
        except Exception:
            if self._page_is_closed():
                raise CollectorRuntimeError(RuntimeReasonCode.BROWSER_CLOSED) from None
            return False
        finally:
            if session is not None:
                try:
                    session.detach()
                except Exception:
                    pass
        return self._wait_for_media_transition(previous_identity, timeout_seconds=5.0)

    def _pointer_wheel_advance(self) -> None:
        target = self._targeted_wheel_point()
        if target is None:
            raise CollectorRuntimeError(RuntimeReasonCode.ACTIVE_REEL_NOT_FOUND)
        try:
            # The accepted live spike wheels from the viewport centre.  The
            # selected video still validates that a real, visible Reel owns
            # this interaction, but Instagram may place controls over that
            # element's geometric centre and ignore a wheel sent there.
            self._page.mouse.move(target[2] / 2, target[3] / 2)
            self._page.mouse.wheel(0, int(target[3] * 0.9))
            self._scroll_target_diagnostics = replace(
                self._scroll_target_diagnostics,
                scroll_target_available=True,
                scroll_target_in_viewport=True,
                mouse_move_performed=True,
            )
        except Exception:
            if self._page_is_closed():
                raise CollectorRuntimeError(RuntimeReasonCode.BROWSER_CLOSED) from None
            raise

    def _scroll_container_advances(self, previous_identity: str) -> bool:
        """Use the spike's real scroll owner first and only accept a media change."""
        try:
            moved = self._page.evaluate(SCROLL_CONTAINER_PROBE)
        except Exception:
            if self._page_is_closed():
                raise CollectorRuntimeError(RuntimeReasonCode.BROWSER_CLOSED) from None
            return False
        if moved is not True:
            return False
        return self._wait_for_media_transition(previous_identity, timeout_seconds=5.0)

    def _keyboard_advances(self, previous_identity: str) -> bool:
        keyboard = getattr(self._page, "keyboard", None)
        press = getattr(keyboard, "press", None)
        if not callable(press):
            return False
        for key in ("ArrowDown", "PageDown"):
            try:
                press(key)
            except Exception:
                if self._page_is_closed():
                    raise CollectorRuntimeError(RuntimeReasonCode.BROWSER_CLOSED) from None
                return False
            if self._wait_for_media_transition(previous_identity, timeout_seconds=4.0):
                return True
        return False

    def _wait_for_media_transition(self, previous_identity: str, *, timeout_seconds: float) -> bool:
        polls = max(1, int(timeout_seconds / self._limits.polling_seconds))
        stable_identity: str | None = None
        for _ in range(polls):
            self._raise_if_closed()
            current_identity = self._active_media_identity()
            if current_identity is not None and current_identity != previous_identity:
                if current_identity == stable_identity:
                    return True
                stable_identity = current_identity
            else:
                stable_identity = None
            self._page.wait_for_timeout(self._limits.polling_seconds * 1000)
        return False

    def wait_for_next(
        self,
        previous_shortcode: str,
        should_stop: Callable[[], bool] | None = None,
    ) -> ReelCandidate | None:
        self._transition_diagnostics = TransitionSamplingDiagnostics()
        polls = max(1, int(self._limits.timeout_seconds / self._limits.polling_seconds))
        stabilization_polls = max(
            1, int(self._limits.stabilization_seconds / self._limits.polling_seconds)
        )
        observed_different = False
        poll_count = unchanged_count = missing_count = 0
        stable_count = 0
        # A one-element holder keeps the identity strictly in process memory
        # while allowing the bounded sampler below to update it.
        stable_media_identity: list[str | None] = [None]
        previous_media_identity = self._transition_media_identity
        self._transition_media_identity = None
        if previous_media_identity is None:
            previous_media_identity = self._active_media_identity()

        def sample() -> ReelCandidate | None:
            nonlocal observed_different, poll_count, unchanged_count, missing_count, stable_count
            if should_stop is not None and should_stop():
                self._transition_diagnostics = TransitionSamplingDiagnostics(
                    poll_count=poll_count,
                    unchanged_sample_count=unchanged_count,
                    missing_candidate_count=missing_count,
                    different_candidate_observed=observed_different,
                    stable_sample_count=stable_count,
                    stop_reason_code="TOTAL_TIMEOUT_REACHED",
                )
                return None
            self._raise_if_closed()
            self._raise_if_controlled_stop()
            try:
                current_media_identity = self._active_media_identity()
                if (
                    current_media_identity is not None
                    and previous_media_identity is not None
                    and current_media_identity != previous_media_identity
                ):
                    observed_different = True
                    if current_media_identity == stable_media_identity[0]:
                        stable_count += 1
                    else:
                        stable_media_identity[0] = current_media_identity
                        stable_count = 1
                else:
                    stable_media_identity[0] = None
                    stable_count = 0
                candidate = None
                post_action_json_observed = (
                    self._feed_json is not None
                    and self._feed_json.observed_after(self._transition_json_checkpoint)
                )
                if stable_count >= 2 and self._feed_json is not None:
                    candidate = self._feed_json.next_after(
                        previous_shortcode,
                        after_observation=self._transition_json_checkpoint,
                    )
                self._page.wait_for_timeout(self._limits.polling_seconds * 1000)
            except CollectorRuntimeError as error:
                self._transition_diagnostics = TransitionSamplingDiagnostics(
                    poll_count=poll_count,
                    unchanged_sample_count=unchanged_count,
                    missing_candidate_count=missing_count,
                    different_candidate_observed=observed_different,
                    stable_sample_count=stable_count,
                    stop_reason_code=error.code.value,
                )
                raise
            except Exception:
                if self._page_is_closed():
                    self._transition_diagnostics = TransitionSamplingDiagnostics(
                        poll_count=poll_count,
                        unchanged_sample_count=unchanged_count,
                        missing_candidate_count=missing_count,
                        different_candidate_observed=observed_different,
                        stable_sample_count=stable_count,
                        stop_reason_code=RuntimeReasonCode.BROWSER_CLOSED.value,
                    )
                    raise CollectorRuntimeError(RuntimeReasonCode.BROWSER_CLOSED) from None
                raise
            poll_count += 1
            if stable_count < 2:
                unchanged_count += 1
            elif candidate is None:
                missing_count += 1
            else:
                self._transition_media_confirmed = False
                self._transition_diagnostics = TransitionSamplingDiagnostics(
                    poll_count=poll_count,
                    unchanged_sample_count=unchanged_count,
                    missing_candidate_count=missing_count,
                    different_candidate_observed=True,
                    stable_sample_count=stable_count,
                    stable_media_identity_observed=True,
                    post_action_json_observed=post_action_json_observed,
                    canonical_confirmation_observed=True,
                )
                return candidate
            return None

        for _ in range(polls):
            confirmed = sample()
            if confirmed is not None:
                return confirmed
            if self._transition_diagnostics.stop_reason_code is not None:
                return None
        # A new central Reel can appear just before the ten-second window ends.
        # Give it a short bounded chance to produce its second stable sample;
        # this happens before, never instead of, the sole permitted retry wheel.
        if observed_different and stable_count < 2:
            for _ in range(stabilization_polls):
                confirmed = sample()
                if confirmed is not None:
                    return confirmed
                if self._transition_diagnostics.stop_reason_code is not None:
                    return None
        self._transition_diagnostics = TransitionSamplingDiagnostics(
            poll_count=poll_count,
            unchanged_sample_count=unchanged_count,
            missing_candidate_count=missing_count,
            different_candidate_observed=observed_different,
            stable_sample_count=stable_count,
            stable_media_identity_observed=stable_count >= 2,
            post_action_json_observed=(
                self._feed_json is not None
                and self._feed_json.observed_after(self._transition_json_checkpoint)
            ),
            stop_reason_code="TRANSITION_TIMEOUT",
        )
        if self._transition_media_confirmed:
            self._force_pointer_wheel_next_advance = True
        return None

    def _active_media_identity(self) -> str | None:
        try:
            result = self._page.evaluate(ACTIVE_MEDIA_IDENTITY_PROBE)
        except Exception:
            return None
        return result if isinstance(result, str) and 1 <= len(result) <= 128 else None

    def _media_changed(self, previous: str | None) -> bool:
        current = self._active_media_identity()
        return previous is not None and current is not None and current != previous

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        _close_runtime(self._context, self._playwright, self._profile_lock)

    def _select_reels_page(self) -> ReelCandidate:
        page_count = 0
        classifications = {"reels": 0, "login": 0, "challenge": 0, "other": 0}
        aggregate = _empty_diagnostics()
        candidates: list[tuple[BrowserPage, ReelCandidate, dict[str, object]]] = []
        limited_found = False
        for page in self._context.pages:
            if page.is_closed():
                continue
            page_count += 1
            if not _is_instagram_page(page):
                classifications["other"] += 1
                continue
            try:
                state = page.evaluate(STATE_PROBE)
            except Exception:
                classifications["other"] += 1
                continue
            if isinstance(state, dict) and state.get("checkpoint"):
                classifications["challenge"] += 1
                continue
            if isinstance(state, dict) and state.get("login"):
                classifications["login"] += 1
                continue
            if isinstance(state, dict) and state.get("limited"):
                classifications["other"] += 1
                limited_found = True
                continue
            try:
                payload = page.evaluate(IDENTITY_PROBE)
            except Exception:
                classifications["other"] += 1
                continue
            page_diagnostics = _diagnostics_from_payload(payload)
            aggregate["video_count"] += page_diagnostics["video_count"]
            aggregate["visible_video_count"] += page_diagnostics["visible_video_count"]
            aggregate["central_video_present"] = bool(
                aggregate["central_video_present"] or page_diagnostics["central_video_present"]
            )
            page_is_reels = bool(
                page_diagnostics["central_video_present"] or _looks_like_reels_path(page)
            )
            candidate = _candidate_from_payload(payload)
            if candidate is not None:
                try:
                    candidate = validate_candidate(candidate)
                except InvalidReelCandidate:
                    classifications["reels" if page_is_reels else "other"] += 1
                    aggregate["extraction_strategy"] = page_diagnostics["extraction_strategy"]
                    aggregate["reason_code"] = RuntimeReasonCode.INVALID_REEL_CANDIDATE.value
                    continue
                classifications["reels" if page_is_reels else "other"] += 1
                candidates.append((page, candidate, page_diagnostics))
            else:
                classifications["reels" if page_is_reels else "other"] += 1
        aggregate["open_page_count"] = page_count
        aggregate["page_classifications"] = classifications
        if candidates:
            selected = next((item for item in candidates if item[0] is self._page), candidates[0])
            self._page = selected[0]
            aggregate.update(selected[2])
            aggregate["open_page_count"] = page_count
            aggregate["page_classifications"] = classifications
            aggregate["reason_code"] = None
            self._diagnostics = aggregate
            return selected[1]
        if classifications["challenge"]:
            aggregate["reason_code"] = RuntimeReasonCode.CHECKPOINT_REQUIRED.value
            self._diagnostics = aggregate
            raise CollectorRuntimeError(RuntimeReasonCode.CHECKPOINT_REQUIRED)
        if classifications["login"]:
            aggregate["reason_code"] = RuntimeReasonCode.AUTH_REQUIRED.value
            self._diagnostics = aggregate
            raise CollectorRuntimeError(RuntimeReasonCode.AUTH_REQUIRED)
        if limited_found:
            aggregate["reason_code"] = RuntimeReasonCode.TEMPORARILY_LIMITED.value
            self._diagnostics = aggregate
            raise CollectorRuntimeError(RuntimeReasonCode.TEMPORARILY_LIMITED)
        aggregate["reason_code"] = RuntimeReasonCode.ACTIVE_REEL_NOT_FOUND.value
        self._diagnostics = aggregate
        raise CollectorRuntimeError(RuntimeReasonCode.ACTIVE_REEL_NOT_FOUND)

    def _candidate_or_none(self) -> ReelCandidate | None:
        try:
            return self._candidate_from_probe()
        except CollectorRuntimeError as error:
            if error.code is RuntimeReasonCode.ACTIVE_REEL_NOT_FOUND:
                return None
            raise

    def _candidate_from_probe(self) -> ReelCandidate:
        payload = self._page.evaluate(IDENTITY_PROBE)
        self._diagnostics = {
            **_empty_diagnostics(),
            **_diagnostics_from_payload(payload),
            "open_page_count": 1,
            "page_classifications": {"reels": 1, "login": 0, "challenge": 0, "other": 0},
        }
        candidate = _candidate_from_payload(payload)
        if candidate is None:
            self._diagnostics["reason_code"] = RuntimeReasonCode.ACTIVE_REEL_NOT_FOUND.value
            raise CollectorRuntimeError(RuntimeReasonCode.ACTIVE_REEL_NOT_FOUND)
        try:
            candidate = validate_candidate(candidate)
        except InvalidReelCandidate as error:
            self._diagnostics["reason_code"] = RuntimeReasonCode.INVALID_REEL_CANDIDATE.value
            raise CollectorRuntimeError(RuntimeReasonCode.INVALID_REEL_CANDIDATE) from error
        self._diagnostics["reason_code"] = None
        return candidate

    def _raise_if_controlled_stop(self) -> None:
        state = self._page.evaluate(STATE_PROBE)
        if not isinstance(state, dict):
            return
        if state.get("checkpoint"):
            raise CollectorRuntimeError(RuntimeReasonCode.CHECKPOINT_REQUIRED)
        if state.get("login"):
            raise CollectorRuntimeError(RuntimeReasonCode.AUTH_REQUIRED)
        if state.get("limited"):
            raise CollectorRuntimeError(RuntimeReasonCode.TEMPORARILY_LIMITED)

    def _raise_if_closed(self) -> None:
        if self._closed or self._page_is_closed():
            raise CollectorRuntimeError(RuntimeReasonCode.BROWSER_CLOSED)

    def _page_is_closed(self) -> bool:
        try:
            return self._page.is_closed()
        except Exception:
            return True

    def _targeted_wheel_point(self) -> tuple[float, float, float, float] | None:
        try:
            payload = self._page.evaluate(SCROLL_TARGET_PROBE)
        except Exception:
            if self._page_is_closed():
                raise CollectorRuntimeError(RuntimeReasonCode.BROWSER_CLOSED) from None
            return None
        if not isinstance(payload, dict) or payload.get("available") is not True:
            return None
        self._scroll_target_diagnostics = replace(self._scroll_target_diagnostics, scroll_target_available=True)
        if payload.get("in_viewport") is not True:
            return None
        values = tuple(payload.get(key) for key in ("x", "y", "width", "height"))
        if any(isinstance(value, bool) or not isinstance(value, int | float) for value in values):
            return None
        x, y, width, height = (float(value) for value in values)
        if not all(math.isfinite(value) for value in (x, y, width, height)):
            return None
        if width <= 0 or height <= 0 or not (0 <= x < width and 0 <= y < height):
            return None
        self._scroll_target_diagnostics = replace(
            self._scroll_target_diagnostics,
            scroll_target_available=True,
            scroll_target_in_viewport=True,
        )
        return x, y, width, height

    def _active_feed_input_target(self) -> tuple[float, float, float] | None:
        self._scroll_target_diagnostics = replace(self._scroll_target_diagnostics, active_feed_probe_attempted=True)
        try:
            payload = self._page.evaluate(ACTIVE_FEED_INPUT_TARGET_PROBE)
        except Exception:
            self._scroll_target_diagnostics = replace(self._scroll_target_diagnostics, active_feed_probe_failed=True)
            if self._page_is_closed():
                raise CollectorRuntimeError(RuntimeReasonCode.BROWSER_CLOSED) from None
            return None
        if not isinstance(payload, dict) or type(payload.get("available")) is not bool:
            self._scroll_target_diagnostics = replace(self._scroll_target_diagnostics, active_feed_probe_failed=True)
            return None
        self._scroll_target_diagnostics = replace(
            self._scroll_target_diagnostics,
            active_feed_probe_evaluated=True,
            **{key: payload.get(key) is True for key in HIT_TEST_DIAGNOSTIC_FLAGS},
            active_feed_central_video_missing=payload["available"] is False,
            active_feed_target_available=payload["available"],
        )
        if payload["available"] is False:
            return None
        if payload.get("in_viewport") is not True:
            return None
        self._scroll_target_diagnostics = replace(self._scroll_target_diagnostics, active_feed_target_in_viewport=True)
        if payload.get("hit_testable") is not True:
            return None
        values = tuple(payload.get(key) for key in ("x", "start_y", "end_y"))
        if any(isinstance(value, bool) or not isinstance(value, int | float) for value in values):
            return None
        x, start_y, end_y = (float(value) for value in values)
        if not all(math.isfinite(value) for value in (x, start_y, end_y)):
            return None
        if not (x >= 0 and 0 <= end_y < start_y):
            return None
        self._scroll_target_diagnostics = replace(
            self._scroll_target_diagnostics,
            active_feed_target_available=True,
            active_feed_target_in_viewport=True,
            active_feed_target_hit_testable=True,
        )
        return x, start_y, end_y


def _candidate_from_payload(payload: object) -> ReelCandidate | None:
    if not isinstance(payload, dict):
        return None
    shortcode = payload.get("shortcode")
    canonical_url = payload.get("canonical_url")
    if not isinstance(shortcode, str) or not isinstance(canonical_url, str):
        return None
    return ReelCandidate(shortcode, canonical_url)


def _diagnostics_from_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return _empty_diagnostics()
    strategy = payload.get("extraction_strategy")
    return {
        "video_count": _nonnegative_integer(payload.get("video_count")),
        "visible_video_count": _nonnegative_integer(payload.get("visible_video_count")),
        "central_video_present": payload.get("central_video_present") is True,
        "extraction_strategy": strategy if strategy in _EXTRACTION_STRATEGIES else "none",
    }


_EXTRACTION_STRATEGIES = frozenset(
    {
        "video_anchor",
        "ancestor_anchor",
        "closest_anchor",
        "ancestor_descendant_anchor",
        "sibling_anchor",
        "sibling_container_anchor",
        "pathname_fallback",
        "none",
    }
)


def _empty_diagnostics() -> dict[str, object]:
    return {
        "open_page_count": 0,
        "page_classifications": {"reels": 0, "login": 0, "challenge": 0, "other": 0},
        "video_count": 0,
        "visible_video_count": 0,
        "central_video_present": False,
        "extraction_strategy": "none",
        "reason_code": None,
    }


def _clear_transient_chromium_locks(profile: Path) -> None:
    """Remove only stale Chromium process locks under an exclusive profile lock."""
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        try:
            (profile / name).unlink()
        except FileNotFoundError:
            pass


def _empty_identity_structure_diagnostics() -> dict[str, int | bool]:
    return {
        "video_count": 0,
        "visible_video_count": 0,
        "central_video_present": False,
        "page_reel_anchor_count": 0,
        "nearby_reel_anchor_count": 0,
        "ancestor_data_attribute_count": 0,
        "location_is_specific_reel": False,
    }


def _identity_structure_from_payload(payload: object) -> dict[str, int | bool]:
    safe = _empty_identity_structure_diagnostics()
    if not isinstance(payload, dict):
        return safe
    for key in (
        "video_count",
        "visible_video_count",
        "page_reel_anchor_count",
        "nearby_reel_anchor_count",
        "ancestor_data_attribute_count",
    ):
        safe[key] = _nonnegative_integer(payload.get(key))
    safe["central_video_present"] = payload.get("central_video_present") is True
    safe["location_is_specific_reel"] = payload.get("location_is_specific_reel") is True
    return safe


def _nonnegative_integer(value: object) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _is_instagram_page(page: BrowserPage) -> bool:
    try:
        parsed = urlparse(page.url)
    except Exception:
        return False
    return parsed.scheme == "https" and parsed.hostname == "www.instagram.com"


def _looks_like_reels_path(page: BrowserPage) -> bool:
    try:
        return urlparse(page.url).path.startswith(("/reel/", "/reels/"))
    except Exception:
        return False


def _close_runtime(context, playwright, lock: ProfileLock | None) -> None:
    """Close runtime resources without replacing a controlled-stop reason."""

    try:
        if context is not None:
            context.close()
    except Exception:
        pass
    try:
        if playwright is not None:
            playwright.stop()
    except Exception:
        pass
    try:
        if lock is not None:
            lock.release()
    except Exception:
        pass

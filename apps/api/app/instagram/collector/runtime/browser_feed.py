"""Bounded Playwright Reels feed adapter; no network observation or page dumps."""

# ruff: noqa: E501  # Embedded JavaScript probes retain readable browser syntax.

import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse
from uuid import UUID

from app.instagram.collector.canonical import InvalidReelCandidate, validate_candidate
from app.instagram.collector.contracts import (
    ReelCandidate,
    ScrollTargetDiagnostics,
    TransitionSamplingDiagnostics,
)
from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode
from app.instagram.collector.runtime.profile_lock import ProfileLock, profile_path
from app.instagram.collector.runtime.settings import CollectorRuntimeSettings

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
            from playwright.sync_api import sync_playwright

            playwright = sync_playwright().start()
            context = playwright.chromium.launch_persistent_context(
                str(profile),
                headless=settings.headless,
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
            return self._select_reels_page()
        self._raise_if_closed()
        self._raise_if_controlled_stop()
        return self._candidate_from_probe()

    def pause_current(self) -> None:
        self._raise_if_closed()
        if self._page.evaluate(PAUSE_PROBE) is not True:
            self._diagnostics["reason_code"] = RuntimeReasonCode.ACTIVE_REEL_NOT_FOUND.value
            raise CollectorRuntimeError(RuntimeReasonCode.ACTIVE_REEL_NOT_FOUND)

    def advance(self) -> None:
        self._raise_if_closed()
        if self._scroll_attempts >= self._limits.maximum_scroll_attempts:
            raise CollectorRuntimeError(RuntimeReasonCode.TRANSITION_TIMEOUT)
        target = self._targeted_wheel_point()
        if target is None:
            raise CollectorRuntimeError(RuntimeReasonCode.ACTIVE_REEL_NOT_FOUND)
        try:
            self._page.mouse.move(*target)
            self._scroll_target_diagnostics = ScrollTargetDiagnostics(
                scroll_target_available=True,
                scroll_target_in_viewport=True,
                mouse_move_performed=True,
            )
            self._page.mouse.wheel(0, 640)
        except Exception:
            if self._page_is_closed():
                raise CollectorRuntimeError(RuntimeReasonCode.BROWSER_CLOSED) from None
            raise
        self._scroll_attempts += 1

    def wait_for_next(
        self,
        previous_shortcode: str,
        should_stop: Callable[[], bool] | None = None,
    ) -> ReelCandidate | None:
        self._transition_diagnostics = TransitionSamplingDiagnostics()
        stable: ReelCandidate | None = None
        polls = max(1, int(self._limits.timeout_seconds / self._limits.polling_seconds))
        stabilization_polls = max(
            1, int(self._limits.stabilization_seconds / self._limits.polling_seconds)
        )
        observed_different = False
        poll_count = unchanged_count = missing_count = 0
        stable_count = 0

        def sample() -> ReelCandidate | None:
            nonlocal stable, observed_different, poll_count, unchanged_count, missing_count, stable_count
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
                candidate = self._candidate_or_none()
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
            if candidate is None:
                missing_count += 1
                stable = None
                stable_count = 0
            elif candidate.shortcode == previous_shortcode:
                unchanged_count += 1
                stable = None
                stable_count = 0
            else:
                observed_different = True
                if stable is not None and stable.shortcode == candidate.shortcode:
                    stable_count += 1
                else:
                    stable = candidate
                    stable_count = 1
                if stable_count >= 2:
                    self._transition_diagnostics = TransitionSamplingDiagnostics(
                        poll_count=poll_count,
                        unchanged_sample_count=unchanged_count,
                        missing_candidate_count=missing_count,
                        different_candidate_observed=True,
                        stable_sample_count=stable_count,
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
            stop_reason_code="TRANSITION_TIMEOUT",
        )
        return None

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

    def _targeted_wheel_point(self) -> tuple[float, float] | None:
        self._scroll_target_diagnostics = ScrollTargetDiagnostics()
        try:
            payload = self._page.evaluate(SCROLL_TARGET_PROBE)
        except Exception:
            if self._page_is_closed():
                raise CollectorRuntimeError(RuntimeReasonCode.BROWSER_CLOSED) from None
            return None
        if not isinstance(payload, dict) or payload.get("available") is not True:
            return None
        self._scroll_target_diagnostics = ScrollTargetDiagnostics(scroll_target_available=True)
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
        self._scroll_target_diagnostics = ScrollTargetDiagnostics(
            scroll_target_available=True,
            scroll_target_in_viewport=True,
        )
        return x, y


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

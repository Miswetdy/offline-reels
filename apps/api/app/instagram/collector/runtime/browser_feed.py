"""Bounded Playwright Reels feed adapter; no network observation or page dumps."""

# ruff: noqa: E501  # Embedded JavaScript probes retain readable browser syntax.

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from app.instagram.collector.canonical import InvalidReelCandidate, validate_candidate
from app.instagram.collector.contracts import ReelCandidate
from app.instagram.collector.runtime.errors import CollectorRuntimeError, RuntimeReasonCode
from app.instagram.collector.runtime.profile_lock import ProfileLock, profile_path
from app.instagram.collector.runtime.settings import CollectorRuntimeSettings

IDENTITY_PROBE = """
() => {
  const midpoint = window.innerHeight / 2;
  const visible = [...document.querySelectorAll('video')].map((video) => {
    const rect = video.getBoundingClientRect();
    const overlap = Math.max(0, Math.min(rect.bottom, window.innerHeight) - Math.max(rect.top, 0));
    if (overlap <= 0) return null;
    let container = video;
    let link = null;
    for (let depth = 0; depth < 10 && container; depth += 1) {
      link = [...(container.querySelectorAll?.('a') || [])]
        .find((candidate) => /^\\/reel\\/[A-Za-z0-9_-]{1,64}\\/$/.test(candidate.pathname));
      if (link) break;
      container = container.parentElement;
    }
    if (!link) return null;
    const match = /^\\/reel\\/([A-Za-z0-9_-]{1,64})\\/$/.exec(link.pathname);
    if (!match) return null;
    return { shortcode: match[1], canonical_url: `https://www.instagram.com/reel/${match[1]}/`, distance: Math.abs((rect.top + rect.bottom) / 2 - midpoint) };
  }).filter(Boolean).sort((left, right) => left.distance - right.distance);
  return visible.length ? { shortcode: visible[0].shortcode, canonical_url: visible[0].canonical_url } : null;
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

STATE_PROBE = """
() => ({
  login: Boolean(document.querySelector('input[name="username"], input[name="password"]')),
  checkpoint: /checkpoint|challenge/.test(location.pathname) || Boolean(document.querySelector('[data-testid="checkpoint"], [data-testid="challenge"]')),
  limited: Boolean(document.querySelector('[data-testid="temporarily-limited"]')),
})
"""


class BrowserPage(Protocol):
    def evaluate(self, expression: str): ...

    def goto(self, url: str, *, wait_until: str): ...

    def wait_for_timeout(self, timeout: float) -> None: ...

    def is_closed(self) -> bool: ...


@dataclass(frozen=True)
class TransitionLimits:
    polling_seconds: float
    timeout_seconds: float
    maximum_scroll_attempts: int


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

    @classmethod
    def open(
        cls,
        account_id: UUID,
        settings: CollectorRuntimeSettings,
        *,
        repository_root: Path,
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
            feed._raise_if_controlled_stop()
            return feed
        except CollectorRuntimeError:
            _close_runtime(context, playwright, lock)
            raise
        except Exception as error:
            _close_runtime(context, playwright, lock)
            raise CollectorRuntimeError(RuntimeReasonCode.BROWSER_CLOSED) from error

    @property
    def cookie_context(self):
        if self._context is None or self._closed:
            raise CollectorRuntimeError(RuntimeReasonCode.BROWSER_CLOSED)
        return self._context

    def current(self) -> ReelCandidate:
        self._raise_if_closed()
        self._raise_if_controlled_stop()
        return self._candidate_from_probe()

    def pause_current(self) -> None:
        self._raise_if_closed()
        if self._page.evaluate(PAUSE_PROBE) is not True:
            raise CollectorRuntimeError(RuntimeReasonCode.ACTIVE_REEL_NOT_FOUND)

    def advance(self) -> None:
        self._raise_if_closed()
        if self._scroll_attempts >= self._limits.maximum_scroll_attempts:
            raise CollectorRuntimeError(RuntimeReasonCode.TRANSITION_TIMEOUT)
        self._page.evaluate("() => window.scrollBy({ top: window.innerHeight * 0.9, behavior: 'instant' })")
        self._scroll_attempts += 1

    def wait_for_next(self, previous_shortcode: str) -> ReelCandidate | None:
        stable: ReelCandidate | None = None
        polls = max(1, int(self._limits.timeout_seconds / self._limits.polling_seconds))
        for _ in range(polls):
            self._raise_if_closed()
            self._raise_if_controlled_stop()
            candidate = self._candidate_or_none()
            if candidate is not None and candidate.shortcode != previous_shortcode:
                if stable is not None and stable.shortcode == candidate.shortcode:
                    return candidate
                stable = candidate
            else:
                stable = None
            self._page.wait_for_timeout(self._limits.polling_seconds * 1000)
        return None

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        _close_runtime(self._context, self._playwright, self._profile_lock)

    def _candidate_or_none(self) -> ReelCandidate | None:
        try:
            return self._candidate_from_probe()
        except CollectorRuntimeError as error:
            if error.code is RuntimeReasonCode.ACTIVE_REEL_NOT_FOUND:
                return None
            raise

    def _candidate_from_probe(self) -> ReelCandidate:
        payload = self._page.evaluate(IDENTITY_PROBE)
        if not isinstance(payload, dict):
            raise CollectorRuntimeError(RuntimeReasonCode.ACTIVE_REEL_NOT_FOUND)
        shortcode = payload.get("shortcode")
        canonical_url = payload.get("canonical_url")
        if not isinstance(shortcode, str) or not isinstance(canonical_url, str):
            raise CollectorRuntimeError(RuntimeReasonCode.ACTIVE_REEL_NOT_FOUND)
        try:
            return validate_candidate(ReelCandidate(shortcode, canonical_url))
        except InvalidReelCandidate as error:
            raise CollectorRuntimeError(RuntimeReasonCode.INVALID_REEL_CANDIDATE) from error

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
        if self._closed or self._page.is_closed():
            raise CollectorRuntimeError(RuntimeReasonCode.BROWSER_CLOSED)


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

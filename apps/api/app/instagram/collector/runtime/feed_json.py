"""Bounded, in-memory canonical Reel IDs observed in authenticated feed JSON."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Protocol

from app.instagram.collector.canonical import SHORTCODE
from app.instagram.collector.contracts import ReelCandidate

_MAX_CODES = 32
_CANONICAL_CODE_KEYS = ("code", "shortcode", "media_code")


class JsonResponse(Protocol):
    @property
    def headers(self) -> dict[str, str]: ...

    def json(self) -> object: ...


class ResponsePage(Protocol):
    def on(self, event: str, handler: Callable[[JsonResponse], None]) -> None: ...


class FeedJsonCandidateCatalog:
    """Extract only validated ``code`` fields; URLs and response bodies never escape."""

    def __init__(self, page: ResponsePage) -> None:
        self._codes: deque[tuple[int, str]] = deque()
        self._seen: set[str] = set()
        self._observation = 0
        page.on("response", self._observe)

    def checkpoint(self) -> int:
        """Return an in-memory boundary before a feed input is sent.

        A code seen before this boundary cannot prove that the input advanced
        the active card.  The value is intentionally process-local and is
        never logged or persisted.
        """

        return self._observation

    def reset_for_feed_navigation(self) -> None:
        """Forget candidates from an earlier page before fixed Reels navigation."""

        self._codes.clear()
        self._seen.clear()
        self._observation = 0

    def next_after(
        self, previous_shortcode: str, *, after_observation: int = 0
    ) -> ReelCandidate | None:
        for index, (observation, code) in enumerate(self._codes):
            if observation <= after_observation or code == previous_shortcode:
                continue
            del self._codes[index]
            return ReelCandidate(code, f"https://www.instagram.com/reel/{code}/")
        return None

    def next_from_current_feed(self, previous_shortcode: str) -> ReelCandidate | None:
        """Reserve one different candidate observed after the current Reels navigation.

        This is used only after a stable media transition and a new post-input
        JSON observation.  It cannot reuse a value from an older page because
        navigation clears this bounded, in-memory catalog.
        """

        for index, (_, code) in enumerate(self._codes):
            if code == previous_shortcode:
                continue
            del self._codes[index]
            return ReelCandidate(code, f"https://www.instagram.com/reel/{code}/")
        return None

    def observed_after(self, observation: int) -> bool:
        """Whether any authenticated JSON response arrived after a boundary."""

        return self._observation > observation

    def _observe(self, response: JsonResponse) -> None:
        try:
            content_type = response.headers.get("content-type", "").lower()
            if "json" not in content_type:
                return
            self._observation += 1
            self._collect(response.json(), observation=self._observation)
        except Exception:
            return

    def _collect(self, payload: object, *, observation: int) -> None:
        stack = [payload]
        visited = 0
        while stack and visited < 20_000:
            visited += 1
            value = stack.pop()
            if isinstance(value, dict):
                for key in _CANONICAL_CODE_KEYS:
                    code = value.get(key)
                    if (
                        isinstance(code, str)
                        and SHORTCODE.fullmatch(code)
                        and code not in self._seen
                    ):
                        self._seen.add(code)
                        self._codes.append((observation, code))
                        if len(self._codes) > _MAX_CODES:
                            self._codes.popleft()
                stack.extend(reversed(tuple(value.values())))
            elif isinstance(value, list):
                stack.extend(reversed(value))

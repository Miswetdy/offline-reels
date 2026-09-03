"""Bounded, in-memory canonical Reel IDs observed in authenticated feed JSON."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Protocol

from app.instagram.collector.canonical import SHORTCODE
from app.instagram.collector.contracts import ReelCandidate

_MAX_CODES = 32


class JsonResponse(Protocol):
    @property
    def headers(self) -> dict[str, str]: ...

    def json(self) -> object: ...


class ResponsePage(Protocol):
    def on(self, event: str, handler: Callable[[JsonResponse], None]) -> None: ...


class FeedJsonCandidateCatalog:
    """Extract only validated ``code`` fields; URLs and response bodies never escape."""

    def __init__(self, page: ResponsePage) -> None:
        self._codes: deque[str] = deque()
        self._seen: set[str] = set()
        page.on("response", self._observe)

    def next_after(self, previous_shortcode: str) -> ReelCandidate | None:
        while self._codes:
            code = self._codes.popleft()
            if code == previous_shortcode:
                continue
            return ReelCandidate(code, f"https://www.instagram.com/reel/{code}/")
        return None

    def _observe(self, response: JsonResponse) -> None:
        try:
            content_type = response.headers.get("content-type", "").lower()
            if "json" not in content_type:
                return
            self._collect(response.json())
        except Exception:
            return

    def _collect(self, payload: object) -> None:
        stack = [payload]
        visited = 0
        while stack and visited < 20_000:
            visited += 1
            value = stack.pop()
            if isinstance(value, dict):
                code = value.get("code")
                if isinstance(code, str) and SHORTCODE.fullmatch(code) and code not in self._seen:
                    self._seen.add(code)
                    self._codes.append(code)
                    if len(self._codes) > _MAX_CODES:
                        self._codes.popleft()
                stack.extend(reversed(tuple(value.values())))
            elif isinstance(value, list):
                stack.extend(reversed(value))

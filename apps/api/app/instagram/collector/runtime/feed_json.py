"""Bounded, in-memory canonical Reel IDs observed in authenticated feed JSON."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Protocol

from app.instagram.collector.canonical import SHORTCODE
from app.instagram.collector.contracts import ReelCandidate

_MAX_CODES = 32
_MAX_KNOWN_CODES = 64
_CANONICAL_CODE_KEYS = ("code", "shortcode", "media_code")
_MAX_WEB_API_SCHEMA_RESPONSES = 2
_MAX_JSON_SCHEMA_RESPONSES_PER_CLASS = 2


class JsonResponse(Protocol):
    @property
    def headers(self) -> dict[str, str]: ...

    def json(self) -> object: ...


class ResponsePage(Protocol):
    def on(self, event: str, handler: Callable[[JsonResponse], None]) -> None: ...


class AuthenticatedFeedSource:
    """Bounded canonical candidates from authenticated Reels-page sources.

    JSON-response candidates are accepted only from GraphQL. Explicit embedded
    JSON scripts on the authenticated `/reels/` document may add validated
    candidates under media-shaped ancestry after the page has loaded. Other
    JSON and all non-JSON response classes remain aggregate diagnostics only.
    Values are held only in the process-local bounded queue and are never
    logged or persisted.
    """

    def __init__(self, page: ResponsePage) -> None:
        self._codes: deque[tuple[int, str]] = deque()
        # Values are kept only for the lifetime of one Collector process.
        # Keeping a bounded session-wide memory prevents a fixed Reels refresh
        # from returning an ID already observed on the previous document.
        self._known_codes: set[str] = set()
        self._known_order: deque[str] = deque()
        self._observation = 0
        self._source_classes = {"graphql": 0, "web_api": 0, "other": 0}
        self._non_json_response_classes = {"html": 0, "javascript": 0, "other": 0}
        self._schema_counts = {
            "media_nodes": 0,
            "canonical_shaped_values": 0,
            "web_api_media_nodes": 0,
            "web_api_canonical_shaped_values": 0,
            "web_api_allowed_canonical_alias_values": 0,
            "web_api_tree_allowed_canonical_alias_values": 0,
            "web_api_schema_responses": 0,
            "graphql_tree_allowed_canonical_alias_values": 0,
            "graphql_schema_responses": 0,
            "other_tree_allowed_canonical_alias_values": 0,
            "other_schema_responses": 0,
        }
        page.on("response", self._observe)

    def checkpoint(self) -> int:
        """Return an in-memory boundary before a feed input is sent.

        A code seen before this boundary cannot prove that the input advanced
        the active card.  The value is intentionally process-local and is
        never logged or persisted.
        """

        return self._observation

    def reset_for_feed_navigation(self) -> None:
        """Discard pending candidates before fixed Reels navigation.

        The bounded session memory remains so the new document can contribute
        only candidates not already observed in this process.  It contains no
        metadata beyond validated canonical IDs and is never persisted.
        """

        self._codes.clear()
        self._observation = 0

    def queue_diagnostics(self) -> dict[str, int]:
        """Return aggregate-only queue state for no-download acceptance."""

        return {
            "pending_candidate_count": len(self._codes),
            "known_candidate_count": len(self._known_codes),
        }

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

    def next_embedded_from_current_feed(self, previous_shortcode: str) -> ReelCandidate | None:
        """Reserve a different candidate supplied by an embedded JSON script only."""

        for index, (observation, code) in enumerate(self._codes):
            if observation != 0 or code == previous_shortcode:
                continue
            del self._codes[index]
            return ReelCandidate(code, f"https://www.instagram.com/reel/{code}/")
        return None

    def observed_after(self, observation: int) -> bool:
        """Whether any authenticated JSON response arrived after a boundary."""

        return self._observation > observation

    def observe_embedded_candidates(self, payload: object) -> None:
        """Add validated IDs from the current Reels document's JSON scripts.

        The browser probe has already restricted this payload to explicit JSON
        script types and media-shaped ancestry. Values from arbitrary inline
        JavaScript, DOM attributes, URLs and response bodies never reach this
        method.
        """

        if not isinstance(payload, list):
            return
        for code in payload[:_MAX_CODES]:
            if (
                not isinstance(code, str)
                or not SHORTCODE.fullmatch(code)
                or code in self._known_codes
            ):
                continue
            self._remember(code)
            self._codes.append((0, code))
            if len(self._codes) > _MAX_CODES:
                self._codes.popleft()

    def mark_used(self, shortcode: str) -> None:
        """Prevent the current or already-reserved Reel from re-entering the queue."""

        if not SHORTCODE.fullmatch(shortcode):
            return
        self._remember(shortcode)
        self._codes = deque(
            (observation, code) for observation, code in self._codes if code != shortcode
        )

    def source_class_counts(self) -> dict[str, int]:
        return dict(self._source_classes)

    def schema_counts(self) -> dict[str, int]:
        return dict(self._schema_counts)

    def non_json_response_class_counts(self) -> dict[str, int]:
        return {f"non_json_{key}": value for key, value in self._non_json_response_classes.items()}

    def _observe(self, response: JsonResponse) -> None:
        try:
            content_type = response.headers.get("content-type", "").lower()
            if "json" not in content_type:
                if "html" in content_type:
                    self._non_json_response_classes["html"] += 1
                elif "javascript" in content_type or "ecmascript" in content_type:
                    self._non_json_response_classes["javascript"] += 1
                else:
                    self._non_json_response_classes["other"] += 1
                return
            url = str(getattr(response, "url", "")).lower()
            source_class = (
                "graphql"
                if "graphql" in url
                else "web_api"
                if "/api/" in url
                else "other"
            )
            self._source_classes[source_class] += 1
            if source_class == "web_api":
                self._inspect_web_api_schema_response(response)
                return
            if source_class == "other":
                self._inspect_other_schema_response(response)
                return
            payload = response.json()
            self._inspect_graphql_schema(payload)
            self._observation += 1
            self._collect(payload, observation=self._observation)
        except Exception:
            return

    def _collect(self, payload: object, *, observation: int) -> None:
        stack = [payload]
        visited = 0
        while stack and visited < 20_000:
            visited += 1
            value = stack.pop()
            if isinstance(value, dict):
                is_media_node = isinstance(value.get("id"), str) and (
                    "media" in str(value.get("__typename", "")).lower()
                    or "video" in str(value.get("__typename", "")).lower()
                )
                if is_media_node:
                    self._schema_counts["media_nodes"] += 1
                    self._schema_counts["canonical_shaped_values"] += sum(
                        bool(isinstance(item, str) and SHORTCODE.fullmatch(item))
                        for item in value.values()
                    )
                for key in _CANONICAL_CODE_KEYS:
                    code = value.get(key)
                    if (
                        isinstance(code, str)
                        and SHORTCODE.fullmatch(code)
                        and code not in self._known_codes
                    ):
                        self._remember(code)
                        self._codes.append((observation, code))
                        if len(self._codes) > _MAX_CODES:
                            self._codes.popleft()
                stack.extend(reversed(tuple(value.values())))
            elif isinstance(value, list):
                stack.extend(reversed(value))

    def _remember(self, code: str) -> None:
        """Keep session deduplication bounded without retaining any metadata."""

        if code in self._known_codes:
            return
        self._known_codes.add(code)
        self._known_order.append(code)
        if len(self._known_order) > _MAX_KNOWN_CODES:
            self._known_codes.discard(self._known_order.popleft())

    def _inspect_web_api_schema_response(self, response: JsonResponse) -> None:
        if self._schema_counts["web_api_schema_responses"] >= _MAX_WEB_API_SCHEMA_RESPONSES:
            return
        self._schema_counts["web_api_schema_responses"] += 1
        self._inspect_web_api_schema(response.json())

    def _inspect_web_api_schema(self, payload: object) -> None:
        stack, visited = [payload], 0
        while stack and visited < 20_000:
            visited += 1
            value = stack.pop()
            if isinstance(value, dict):
                self._schema_counts["web_api_tree_allowed_canonical_alias_values"] += sum(
                    bool(
                        isinstance(value.get(key), str)
                        and SHORTCODE.fullmatch(value[key])
                    )
                    for key in _CANONICAL_CODE_KEYS
                )
                if "media_type" in value or "video_versions" in value:
                    self._schema_counts["web_api_media_nodes"] += 1
                    self._schema_counts["web_api_canonical_shaped_values"] += sum(
                        bool(isinstance(item, str) and SHORTCODE.fullmatch(item))
                        for item in value.values()
                    )
                    self._schema_counts["web_api_allowed_canonical_alias_values"] += sum(
                        bool(
                            isinstance(value.get(key), str)
                            and SHORTCODE.fullmatch(value[key])
                        )
                        for key in _CANONICAL_CODE_KEYS
                    )
                stack.extend(reversed(tuple(value.values())))
            elif isinstance(value, list):
                stack.extend(reversed(value))

    def _inspect_graphql_schema(self, payload: object) -> None:
        self._inspect_tree_aliases("graphql", payload)

    def _inspect_other_schema_response(self, response: JsonResponse) -> None:
        self._inspect_tree_aliases("other", response.json())

    def _inspect_tree_aliases(self, source_class: str, payload: object) -> None:
        response_key = f"{source_class}_schema_responses"
        alias_key = f"{source_class}_tree_allowed_canonical_alias_values"
        if self._schema_counts[response_key] >= _MAX_JSON_SCHEMA_RESPONSES_PER_CLASS:
            return
        self._schema_counts[response_key] += 1
        stack, visited = [payload], 0
        while stack and visited < 20_000:
            visited += 1
            value = stack.pop()
            if isinstance(value, dict):
                self._schema_counts[alias_key] += sum(
                    bool(
                        isinstance(value.get(key), str)
                        and SHORTCODE.fullmatch(value[key])
                    )
                    for key in _CANONICAL_CODE_KEYS
                )
                stack.extend(reversed(tuple(value.values())))
            elif isinstance(value, list):
                stack.extend(reversed(value))


# Compatibility name retained while callers migrate to the explicit source boundary.
FeedJsonCandidateCatalog = AuthenticatedFeedSource

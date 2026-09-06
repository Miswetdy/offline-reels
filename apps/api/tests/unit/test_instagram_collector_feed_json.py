from app.instagram.collector.runtime.feed_json import FeedJsonCandidateCatalog


class _Page:
    def on(self, event, handler):
        assert event == "response"
        self.handler = handler


class _Response:
    def __init__(
        self,
        payload,
        content_type="application/json",
        url="https://www.instagram.com/graphql/query/",
    ):
        self.headers = {"content-type": content_type}
        self._payload = payload
        self.url = url

    def json(self):
        return self._payload


def test_catalog_accepts_only_bounded_valid_unique_codes():
    page = _Page()
    catalog = FeedJsonCandidateCatalog(page)
    page.handler(
        _Response(
            {
                "items": [
                    {"code": "FIRST_1"},
                    {"code": "FIRST_1"},
                    {"code": "bad space"},
                    {"nested": {"code": "SECOND_2"}},
                ]
            }
        )
    )

    first = catalog.next_after("PREVIOUS")
    second = catalog.next_after("FIRST_1")

    assert first is not None and first.shortcode == "FIRST_1"
    assert second is not None and second.shortcode == "SECOND_2"
    assert catalog.next_after("SECOND_2") is None


def test_catalog_ignores_non_json_and_malformed_responses():
    page = _Page()
    catalog = FeedJsonCandidateCatalog(page)
    page.handler(_Response({"code": "IGNORED_1"}, "text/html"))
    assert catalog.next_after("PREVIOUS") is None


def test_catalog_only_returns_codes_observed_after_transition_checkpoint():
    page = _Page()
    catalog = FeedJsonCandidateCatalog(page)
    page.handler(_Response({"code": "STALE_1"}))
    checkpoint = catalog.checkpoint()
    page.handler(_Response({"code": "FRESH_2"}))

    candidate = catalog.next_after("PREVIOUS", after_observation=checkpoint)

    assert candidate is not None
    assert candidate.shortcode == "FRESH_2"


def test_catalog_reserves_preloaded_current_feed_candidate_only_on_explicit_fallback():
    page = _Page()
    catalog = FeedJsonCandidateCatalog(page)
    page.handler(_Response({"code": "CURRENT_1"}))
    page.handler(_Response({"code": "QUEUED_2"}))
    checkpoint = catalog.checkpoint()

    assert catalog.next_after("CURRENT_1", after_observation=checkpoint) is None
    fallback = catalog.next_from_current_feed("CURRENT_1")

    assert fallback is not None
    assert fallback.shortcode == "QUEUED_2"


def test_catalog_reset_does_not_leak_candidates_across_feed_navigation():
    page = _Page()
    catalog = FeedJsonCandidateCatalog(page)
    page.handler(_Response({"code": "OLD_FEED_1"}))
    catalog.reset_for_feed_navigation()
    page.handler(_Response({"code": "CURRENT_FEED_2"}))

    candidate = catalog.next_from_current_feed("PREVIOUS")

    assert candidate is not None
    assert candidate.shortcode == "CURRENT_FEED_2"


def test_catalog_accepts_only_valid_canonical_code_aliases():
    page = _Page()
    catalog = FeedJsonCandidateCatalog(page)
    page.handler(
        _Response(
            {
                "shortcode": "SHORTCODE_2",
                "media_code": "MEDIA_CODE_3",
                "unrelated_code": "NOT_COLLECTED_4",
                "code": "INVALID.CODE",
            }
        )
    )

    first = catalog.next_from_current_feed("PREVIOUS")
    second = catalog.next_from_current_feed("PREVIOUS")

    assert first is not None and first.shortcode == "SHORTCODE_2"
    assert second is not None and second.shortcode == "MEDIA_CODE_3"
    assert catalog.next_from_current_feed("PREVIOUS") is None


def test_catalog_inspects_only_two_web_api_responses_as_aggregate_schema():
    page = _Page()
    catalog = FeedJsonCandidateCatalog(page)
    web_api_url = "https://www.instagram.com/api/v1/feed/reels_tray/"

    for code in ("WEB_API_1", "WEB_API_2", "WEB_API_3"):
        page.handler(
            _Response(
                {
                    "items": [
                        {
                            "media_type": 2,
                            "code": code,
                            "unrelated": "CANONICAL_SHAPED_ONLY",
                            "video_versions": [],
                        }
                    ],
                    "nested": {"shortcode": "WEB_API_TREE_CODE"},
                },
                url=web_api_url,
            )
        )

    assert catalog.source_class_counts() == {"graphql": 0, "web_api": 3, "other": 0}
    assert catalog.schema_counts() == {
        "media_nodes": 0,
        "canonical_shaped_values": 0,
        "web_api_media_nodes": 2,
        "web_api_canonical_shaped_values": 4,
        "web_api_allowed_canonical_alias_values": 2,
        "web_api_tree_allowed_canonical_alias_values": 4,
        "web_api_schema_responses": 2,
        "graphql_tree_allowed_canonical_alias_values": 0,
        "graphql_schema_responses": 0,
        "other_tree_allowed_canonical_alias_values": 0,
        "other_schema_responses": 0,
    }
    assert catalog.next_from_current_feed("PREVIOUS") is None


def test_catalog_inspects_only_two_other_json_responses_as_aggregate_schema():
    page = _Page()
    catalog = FeedJsonCandidateCatalog(page)

    for code in ("OTHER_JSON_1", "OTHER_JSON_2", "OTHER_JSON_3"):
        page.handler(_Response({"code": code}, url="https://www.instagram.com/data/"))

    assert catalog.source_class_counts() == {"graphql": 0, "web_api": 0, "other": 3}
    assert catalog.schema_counts() == {
        "media_nodes": 0,
        "canonical_shaped_values": 0,
        "web_api_media_nodes": 0,
        "web_api_canonical_shaped_values": 0,
        "web_api_allowed_canonical_alias_values": 0,
        "web_api_tree_allowed_canonical_alias_values": 0,
        "web_api_schema_responses": 0,
        "graphql_tree_allowed_canonical_alias_values": 0,
        "graphql_schema_responses": 0,
        "other_tree_allowed_canonical_alias_values": 2,
        "other_schema_responses": 2,
    }
    assert catalog.next_from_current_feed("PREVIOUS") is None

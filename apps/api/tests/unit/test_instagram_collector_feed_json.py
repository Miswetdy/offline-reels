from app.instagram.collector.runtime.feed_json import FeedJsonCandidateCatalog


class _Page:
    def on(self, event, handler):
        assert event == "response"
        self.handler = handler


class _Response:
    url = "https://www.instagram.com/graphql/query/"

    def __init__(self, payload, content_type="application/json"):
        self.headers = {"content-type": content_type}
        self._payload = payload

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

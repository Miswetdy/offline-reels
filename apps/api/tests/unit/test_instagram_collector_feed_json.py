from app.instagram.collector.runtime.feed_json import FeedJsonCandidateCatalog


class _Page:
    def on(self, event, handler):
        assert event == "response"
        self.handler = handler


class _Response:
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

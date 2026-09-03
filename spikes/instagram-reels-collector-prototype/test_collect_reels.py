from collect_reels import ActiveVideo, _wait_for_transition


class FakePage:
    def __init__(self, samples):
        self.samples = iter(samples)

    def evaluate(self, _probe):
        return next(self.samples)

    def wait_for_timeout(self, _milliseconds):
        pass


def test_transition_accepts_new_media_after_two_stable_samples():
    previous = ActiveVideo("https://cdn.invalid/one", "one", 10.0)
    page = FakePage([
        {"source": "https://cdn.invalid/one", "ready": 4},
        {"source": "https://cdn.invalid/two", "ready": 4},
        {"source": "https://cdn.invalid/two", "ready": 4},
    ])
    # The fingerprint function hashes the source; provide the matching previous hash.
    import hashlib
    previous = ActiveVideo(previous.source, hashlib.sha256(previous.source.encode()).hexdigest(), 10.0)
    assert _wait_for_transition(page, previous, timeout_seconds=1).source.endswith("two")

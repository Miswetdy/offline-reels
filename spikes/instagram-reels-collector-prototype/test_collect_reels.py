from collect_reels import ActiveVideo, _wait_for_transition


class FakePage:
    def __init__(self, samples):
        self.samples = iter(samples)

    def evaluate(self, _probe):
        return next(self.samples)

    def wait_for_timeout(self, _milliseconds):
        pass


def test_transition_accepts_new_media_after_two_stable_samples():
    previous = ActiveVideo("one", "one", 10.0)
    page = FakePage([
        {"identity": "one", "ready": 4},
        {"identity": "two", "ready": 4},
        {"identity": "two", "ready": 4},
    ])
    # The fingerprint function hashes the DOM media identity.
    import hashlib
    previous = ActiveVideo(previous.identity, hashlib.sha256(previous.identity.encode()).hexdigest(), 10.0)
    assert _wait_for_transition(page, previous, timeout_seconds=1).identity != previous.identity

"""Production-owned canonical Reel candidate validation."""

import re
from urllib.parse import urlsplit

from app.instagram.collector.contracts import ReelCandidate

SHORTCODE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class InvalidReelCandidate(ValueError):
    pass


def validate_candidate(candidate: ReelCandidate) -> ReelCandidate:
    if not SHORTCODE.fullmatch(candidate.shortcode):
        raise InvalidReelCandidate("Invalid shortcode.")
    try:
        parsed = urlsplit(candidate.canonical_url)
        port = parsed.port
    except (TypeError, ValueError) as error:
        raise InvalidReelCandidate("Invalid canonical Reel URL.") from error
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.instagram.com"
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path != f"/reel/{candidate.shortcode}/"
    ):
        raise InvalidReelCandidate("Invalid canonical Reel URL.")
    return candidate


def source_object_key(shortcode: str) -> str:
    if not SHORTCODE.fullmatch(shortcode):
        raise InvalidReelCandidate("Invalid shortcode.")
    return f"instagram-sources/{shortcode}.mp4"

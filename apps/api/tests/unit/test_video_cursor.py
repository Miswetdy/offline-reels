import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.services.video_cursor import (
    MAX_CURSOR_LENGTH,
    InvalidVideoCursor,
    VideoCursor,
    decode_video_cursor,
    encode_video_cursor,
)

SECRET = "test-only-video-cursor-secret-with-at-least-32-characters"


def signed_cursor(payload: dict[str, object]) -> str:
    encoded_payload = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).rstrip(b"=").decode()
    signature = hmac.new(SECRET.encode(), encoded_payload.encode(), hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return f"v1.{encoded_payload}.{encoded_signature}"


def test_cursor_round_trip() -> None:
    cursor = VideoCursor(created_at=datetime(2026, 7, 20, 12, 0, tzinfo=UTC), id=uuid4())

    encoded = encode_video_cursor(cursor, SECRET)

    assert encoded.startswith("v1.")
    assert decode_video_cursor(encoded, SECRET) == cursor


@pytest.mark.parametrize(
    "value",
    [
        "v1.not-base64.not-base64",
        "not-a-cursor",
        "v2.payload.signature",
        "x" * (MAX_CURSOR_LENGTH + 1),
    ],
)
def test_cursor_rejects_malformed_values(value: str) -> None:
    with pytest.raises(InvalidVideoCursor):
        decode_video_cursor(value, SECRET)


def test_cursor_rejects_invalid_signature_and_tampered_payload() -> None:
    valid = encode_video_cursor(VideoCursor(datetime.now(UTC), uuid4()), SECRET)
    prefix, payload, signature = valid.split(".")
    # The final character of an unpadded base64url HMAC can contain unused
    # bits. Change the first significant character so decoded bytes always
    # differ and this integrity assertion remains deterministic.
    tampered_signature = ("A" if signature[0] != "A" else "B") + signature[1:]

    with pytest.raises(InvalidVideoCursor):
        decode_video_cursor(f"{prefix}.{payload}.{tampered_signature}", SECRET)

    tampered_payload = base64.urlsafe_b64encode(
        b'{"version":1,"created_at":"2026-07-20T00:00:00Z","id":"tampered"}'
    ).rstrip(b"=").decode()
    with pytest.raises(InvalidVideoCursor):
        decode_video_cursor(f"{prefix}.{tampered_payload}.{signature}", SECRET)


@pytest.mark.parametrize(
    "payload",
    [
        {"version": 2, "created_at": "2026-07-20T00:00:00Z", "id": str(uuid4())},
        {"version": 1, "created_at": "2026-07-20T00:00:00", "id": str(uuid4())},
        {"version": 1, "created_at": "2026-07-20T00:00:00Z", "id": "not-a-uuid"},
    ],
)
def test_cursor_rejects_invalid_payload(payload: dict[str, object]) -> None:
    with pytest.raises(InvalidVideoCursor):
        decode_video_cursor(signed_cursor(payload), SECRET)


def test_cursor_payload_does_not_contain_secret() -> None:
    cursor = encode_video_cursor(VideoCursor(datetime.now(UTC), UUID(int=1)), SECRET)

    assert SECRET not in cursor

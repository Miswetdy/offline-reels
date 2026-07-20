"""Opaque, signed cursors used by the video feed API."""

import base64
import binascii
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

MAX_CURSOR_LENGTH = 512
_BASE64URL_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class InvalidVideoCursor(Exception):
    """Raised when a client-supplied cursor cannot be safely decoded."""


@dataclass(frozen=True)
class VideoCursor:
    created_at: datetime
    id: UUID


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_base64url(value: str) -> bytes:
    if not value or not _BASE64URL_PATTERN.fullmatch(value):
        raise InvalidVideoCursor
    padding = "=" * (-len(value) % 4)
    try:
        return base64.b64decode(value + padding, altchars=b"-_", validate=True)
    except (ValueError, binascii.Error):
        raise InvalidVideoCursor from None


def _cursor_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Cursor timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def encode_video_cursor(cursor: VideoCursor, secret: str) -> str:
    payload = json.dumps(
        {
            "version": 1,
            "created_at": _cursor_timestamp(cursor.created_at),
            "id": str(cursor.id),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded_payload = _encode_base64url(payload)
    signature = hmac.new(
        secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256
    ).digest()
    return f"v1.{encoded_payload}.{_encode_base64url(signature)}"


def decode_video_cursor(value: str, secret: str) -> VideoCursor:
    if len(value) > MAX_CURSOR_LENGTH:
        raise InvalidVideoCursor

    try:
        prefix, encoded_payload, encoded_signature = value.split(".")
    except ValueError:
        raise InvalidVideoCursor from None
    if prefix != "v1":
        raise InvalidVideoCursor

    payload_bytes = _decode_base64url(encoded_payload)
    signature = _decode_base64url(encoded_signature)
    expected_signature = hmac.new(
        secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(signature, expected_signature):
        raise InvalidVideoCursor

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
        if not isinstance(payload, dict) or set(payload) != {"version", "created_at", "id"}:
            raise ValueError
        if payload["version"] != 1:
            raise ValueError
        created_at = datetime.fromisoformat(str(payload["created_at"]).replace("Z", "+00:00"))
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError
        video_id = UUID(str(payload["id"]))
    except (TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        raise InvalidVideoCursor from None

    return VideoCursor(created_at=created_at.astimezone(UTC), id=video_id)

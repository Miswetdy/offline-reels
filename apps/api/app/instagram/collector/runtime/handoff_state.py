"""Small file-backed control plane for one Collector-process operator handoff.

The state directory is a private, shared Docker volume.  It deliberately holds
only a random grant hash and compact state codes: never browser/profile data.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

HANDOFF_TTL = timedelta(minutes=10)
_TERMINAL = frozenset({"confirmed", "cancelled", "expired", "disconnected"})


@dataclass(frozen=True)
class CreatedHandoff:
    session_id: UUID
    launch_token: str
    expires_at: datetime


class HandoffStateStore:
    def __init__(self, root: Path, now=None) -> None:
        self._root = root.resolve(strict=False)
        self._now = now or (lambda: datetime.now(UTC))

    def create(self, *, ttl: timedelta = HANDOFF_TTL) -> CreatedHandoff:
        if ttl <= timedelta() or ttl > HANDOFF_TTL:
            raise ValueError("invalid handoff ttl")
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        session_id, token, now = uuid4(), secrets.token_urlsafe(32), self._now()
        payload = {
            "state": "pending",
            "token_hash": _hash(token),
            "expires_at": (now + ttl).isoformat(),
        }
        self._write(session_id, payload)
        secret_path = self._root / f".{session_id}.launch"
        secret_path.write_text(token + "\n", encoding="utf-8")
        secret_path.chmod(0o600)
        return CreatedHandoff(session_id, token, now + ttl)

    def activate(self, session_id: UUID, token: str) -> str:
        payload = self._load(session_id)
        if payload is None or not secrets.compare_digest(
            str(payload.get("token_hash", "")), _hash(token)
        ):
            return "unavailable"
        state = self._expire(payload)
        if state != "pending":
            return "unavailable"
        payload["state"] = "active"
        self._write(session_id, payload)
        try:
            (self._root / f".{session_id}.launch").unlink()
        except OSError:
            pass
        return "active"

    def state(self, session_id: UUID) -> str:
        payload = self._load(session_id)
        if payload is None:
            return "unavailable"
        state = self._expire(payload)
        if state == "expired":
            self._write(session_id, payload)
        return state

    def resolve(self, session_id: UUID, *, confirmed: bool) -> str:
        payload = self._load(session_id)
        if payload is None:
            return "unavailable"
        state = self._expire(payload)
        if state != "active":
            if state == "expired":
                self._write(session_id, payload)
            return state
        payload["state"] = "confirmed" if confirmed else "cancelled"
        self._write(session_id, payload)
        return str(payload["state"])

    def _path(self, session_id: UUID) -> Path:
        return self._root / f"{session_id}.json"

    def _load(self, session_id: UUID) -> dict[str, object] | None:
        try:
            value = json.loads(self._path(session_id).read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def _write(self, session_id: UUID, payload: dict[str, object]) -> None:
        destination = self._path(session_id)
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(destination)

    def _expire(self, payload: dict[str, object]) -> str:
        if payload.get("state") in _TERMINAL:
            return str(payload["state"])
        try:
            expires_at = datetime.fromisoformat(str(payload["expires_at"])).astimezone(UTC)
        except (KeyError, ValueError):
            payload["state"] = "expired"
            return "expired"
        if expires_at <= self._now():
            payload["state"] = "expired"
        return str(payload["state"])


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

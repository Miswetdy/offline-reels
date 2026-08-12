"""Local operator commands for Stage 6 device pairing.

The pairing secret is written to the operator terminal only. It is never sent
to FastAPI logs, persisted in clear text, or intended for chat/email transport.
"""

from __future__ import annotations

import argparse
import json
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import update

from app.api.management import hash_secret
from app.core.settings import get_settings
from app.db.models.instagram import (
    InstagramAccount,
    ManagementDeviceSession,
    ManagementPairingChallenge,
)
from app.db.session import create_session_factory
from app.instagram.contracts import AccountStatus


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 6 local management operator commands")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-pairing")
    create.add_argument("--account-id", required=True, type=UUID)
    create.add_argument("--ttl-minutes", required=False, type=int, default=10, choices=range(1, 31))
    revoke = commands.add_parser("revoke-all")
    revoke.add_argument("--account-id", required=True, type=UUID)
    arguments = parser.parse_args(argv)
    sessions = create_session_factory(get_settings())
    if arguments.command == "create-pairing":
        secret = secrets.token_urlsafe(24)
        expires_at = datetime.now(UTC) + timedelta(minutes=arguments.ttl_minutes)
        with sessions.begin() as db:
            if db.get(InstagramAccount, arguments.account_id) is None:
                db.add(
                    InstagramAccount(
                        id=arguments.account_id, status=AccountStatus.DISCONNECTED.value
                    )
                )
            challenge = ManagementPairingChallenge(
                account_id=arguments.account_id,
                secret_hash=hash_secret(secret),
                expires_at=expires_at,
            )
            db.add(challenge)
            db.flush()
            challenge_id = challenge.id
        print(json.dumps({"challenge_id": str(challenge_id), "expires_at": expires_at.isoformat()}))
        print("PAIRING_SECRET=" + secret)
        return 0
    with sessions.begin() as db:
        result = db.execute(
            update(ManagementDeviceSession)
            .where(
                ManagementDeviceSession.account_id == arguments.account_id,
                ManagementDeviceSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
    print(json.dumps({"revoked": result.rowcount}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

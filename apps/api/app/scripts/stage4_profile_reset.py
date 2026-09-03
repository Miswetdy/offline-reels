"""One-shot destructive profile reset, isolated from the public gateway."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.db.models.instagram import InstagramAccount, InstagramLoginSession
from app.db.session import create_session_factory
from app.instagram.contracts import AccountStatus, LoginSessionStatus
from app.instagram.login_gateway import LoginGatewaySettings
from app.instagram.transitions import ACCOUNT_TRANSITIONS, require_transition


def main() -> int:
    account_id = UUID(os.environ["LOGIN_RESET_ACCOUNT_ID"])
    confirmation = UUID(os.environ["LOGIN_RESET_CONFIRM_ACCOUNT"])
    if confirmation != account_id or os.environ.get("LOGIN_RESET_DELETE_PROFILE") != "true":
        return 2
    settings = LoginGatewaySettings()
    sessions = create_session_factory(settings)
    with sessions() as db:
        active = db.scalar(
            select(InstagramLoginSession.id).where(
                InstagramLoginSession.account_id == account_id,
                InstagramLoginSession.status.in_(
                    (LoginSessionStatus.PENDING.value, LoginSessionStatus.ACTIVE.value)
                ),
            )
        )
    if active is not None:
        return 2
    root = Path("/login-profiles").resolve()
    target = (root / str(account_id)).resolve()
    if root not in target.parents:
        return 2
    if target.exists():
        shutil.rmtree(target)
    with sessions.begin() as db:
        account = db.get(InstagramAccount, account_id, with_for_update=True)
        if account is not None:
            current = AccountStatus(account.status)
            if current is not AccountStatus.DISCONNECTED:
                require_transition(ACCOUNT_TRANSITIONS, current, AccountStatus.DISCONNECTED)
                account.status = AccountStatus.DISCONNECTED.value
            account.reason_code = None
    print('{"status":"profile_reset"}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

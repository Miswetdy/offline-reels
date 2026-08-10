"""Operator-only commands for Stage 4 remote Instagram login.

No command accepts credentials, cookies, a 2FA code, or a CAPTCHA response.
"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
from datetime import timedelta
from urllib.request import Request, urlopen
from uuid import UUID

from app.db.models.instagram import InstagramAccount
from app.db.session import create_session_factory
from app.instagram.contracts import AccountStatus
from app.instagram.login_gateway import LoginGatewaySettings
from app.instagram.login_sessions import LoginSessionError, LoginSessionService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage 4 remote-login operator commands")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-link")
    create.add_argument("--account-id", type=UUID, required=True)
    create.add_argument("--ttl-minutes", type=int, default=15, choices=range(1, 16))
    create.add_argument("--profile-check", action="store_true")
    create.add_argument("--confirm-account", type=UUID)
    status = commands.add_parser("status")
    status.add_argument("--session-id", type=UUID, required=True)
    cancel = commands.add_parser("cancel")
    cancel.add_argument("--session-id", type=UUID, required=True)
    verify = commands.add_parser("verify-account")
    verify.add_argument("--account-id", type=UUID, required=True)
    reset = commands.add_parser("reset-profile")
    reset.add_argument("--account-id", type=UUID, required=True)
    reset.add_argument("--confirm-account", type=UUID, required=True)
    reset.add_argument("--confirm-delete-profile", action="store_true")
    arguments = parser.parse_args(argv)
    settings = LoginGatewaySettings()
    service = LoginSessionService(create_session_factory(settings))
    if arguments.command == "create-link":
        if arguments.profile_check and arguments.confirm_account != arguments.account_id:
            print(json.dumps({"status": "rejected"}))
            return 2
        return _create_link(
            service,
            settings,
            arguments.account_id,
            arguments.ttl_minutes,
            arguments.profile_check,
        )
    if arguments.command == "status":
        return _status(service, arguments.session_id)
    if arguments.command == "cancel":
        return _cancel(service, settings, arguments.session_id)
    if arguments.command == "verify-account":
        return _verify_account(settings, arguments.account_id)
    # The public gateway no longer mounts browser profiles.  The host-side
    # reset command runs an isolated UID 10002 one-shot job instead.
    print(json.dumps({"status": "rejected", "reason": "use_host_profile_reset_command"}))
    return 2


def _create_link(
    service: LoginSessionService,
    settings: LoginGatewaySettings,
    account_id: UUID,
    ttl: int,
    profile_check: bool = False,
) -> int:
    try:
        created = service.create(
            account_id,
            timedelta(minutes=ttl),
            allow_connected_profile_check=profile_check,
        )
    except LoginSessionError as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}))
        return 2
    print(
        json.dumps(
            {
                "account_id": str(account_id),
                "session_id": str(created.session_id),
                "expires_at": created.expires_at.isoformat(),
                "status": "pending",
            }
        )
    )
    print(
        f"Launch URL (sensitive; shown once, do not paste into logs): {settings.origin}/connect/{created.session_id}#{created.launch_token}"
    )
    print(
        f"Fallback URL for clients that strip '#': {settings.origin}/connect/{created.session_id}?launch_token={created.launch_token}"
    )
    return 0


def _status(service: LoginSessionService, session_id: UUID) -> int:
    value = service.status(session_id)
    print(
        json.dumps({"session_id": str(session_id), "status": value.value if value else "not_found"})
    )
    return 0 if value else 2


def _cancel(service: LoginSessionService, settings: LoginGatewaySettings, session_id: UUID) -> int:
    try:
        status = service.cancel(session_id)
    except LoginSessionError:
        print(json.dumps({"session_id": str(session_id), "status": "not_found"}))
        return 2
    _close_browser(settings)
    print(json.dumps({"session_id": str(session_id), "status": status.value}))
    return 0


def _verify_account(settings: LoginGatewaySettings, account_id: UUID) -> int:
    sessions = create_session_factory(settings)
    with sessions() as db:
        account = db.get(InstagramAccount, account_id)
    status = AccountStatus.DISCONNECTED if account is None else AccountStatus(account.status)
    print(json.dumps({"account_id": str(account_id), "status": status.value}))
    return 0 if status is AccountStatus.CONNECTED else 2


def _close_browser(settings: LoginGatewaySettings) -> None:
    request = Request(
        f"{str(settings.browser_control_url).rstrip('/')}/shutdown",
        method="POST",
        headers={"X-Login-Browser-Control": settings.browser_control_secret},
    )
    try:
        with urlopen(request, timeout=3):
            pass
    except OSError:
        return


if __name__ == "__main__":
    raise SystemExit(main())

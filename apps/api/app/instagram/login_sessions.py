"""Durable, redacted state machine for a remote Instagram login session."""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models.instagram import InstagramAccount, InstagramLoginSession
from app.instagram.contracts import AccountStatus, LoginSessionStatus, ReasonCode
from app.instagram.transitions import ACCOUNT_TRANSITIONS, require_transition

DEFAULT_LOGIN_TTL = timedelta(minutes=15)


class LoginSessionError(ValueError):
    """A safe state error; it deliberately carries no browser or token detail."""


@dataclass(frozen=True)
class CreatedLoginSession:
    session_id: UUID
    account_id: UUID
    expires_at: datetime
    launch_token: str


def hash_launch_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class LoginSessionService:
    def __init__(
        self, sessions: sessionmaker[Session], now: Callable[[], datetime] | None = None
    ) -> None:
        self._sessions = sessions
        self._now = now or (lambda: datetime.now(UTC))

    def create(
        self,
        account_id: UUID,
        ttl: timedelta = DEFAULT_LOGIN_TTL,
        *,
        allow_connected_profile_check: bool = False,
    ) -> CreatedLoginSession:
        try:
            with self._sessions.begin() as db:
                return self.create_in_transaction(
                    db,
                    account_id,
                    ttl,
                    allow_connected_profile_check=allow_connected_profile_check,
                )
        except IntegrityError as error:
            raise LoginSessionError("An active login session already exists.") from error

    def create_in_transaction(
        self,
        db: Session,
        account_id: UUID,
        ttl: timedelta = DEFAULT_LOGIN_TTL,
        *,
        allow_connected_profile_check: bool = False,
    ) -> CreatedLoginSession:
        """Create using a caller-owned transaction for management idempotency."""
        if ttl <= timedelta() or ttl > DEFAULT_LOGIN_TTL:
            raise LoginSessionError("Invalid login-session lifetime.")
        token = secrets.token_urlsafe(32)
        now = self._now()
        session_id = uuid4()
        # Expiry is a durable state transition, not merely a display concern.
        active_sessions = db.scalars(
            select(InstagramLoginSession)
            .where(
                InstagramLoginSession.account_id == account_id,
                InstagramLoginSession.status.in_(
                    (LoginSessionStatus.PENDING.value, LoginSessionStatus.ACTIVE.value)
                ),
            )
            .with_for_update()
        ).all()
        for active_session in active_sessions:
            self._expire_locked(db, active_session)
        if any(
            active_session.status
            in {LoginSessionStatus.PENDING.value, LoginSessionStatus.ACTIVE.value}
            for active_session in active_sessions
        ):
            raise LoginSessionError("An active login session already exists.")
        account = db.get(InstagramAccount, account_id)
        if account is None:
            account = InstagramAccount(id=account_id, status=AccountStatus.DISCONNECTED.value)
            db.add(account)
            db.flush()
        prior = AccountStatus(account.status)
        allowed = {AccountStatus.DISCONNECTED, AccountStatus.REAUTH_REQUIRED}
        if allow_connected_profile_check:
            allowed.add(AccountStatus.CONNECTED)
        if prior not in allowed:
            raise LoginSessionError("Account cannot start a login session now.")
        if prior is not AccountStatus.CONNECTED:
            require_transition(ACCOUNT_TRANSITIONS, prior, AccountStatus.CONNECTING)
            account.status = AccountStatus.CONNECTING.value
        db.add(
            InstagramLoginSession(
                id=session_id,
                account_id=account_id,
                status=LoginSessionStatus.PENDING.value,
                prior_account_status=prior.value,
                launch_token_hash=hash_launch_token(token),
                expires_at=now + ttl,
            )
        )
        return CreatedLoginSession(session_id, account_id, now + ttl, token)

    def activate(self, session_id: UUID, token: str) -> LoginSessionStatus:
        with self._sessions.begin() as db:
            item = db.scalar(
                select(InstagramLoginSession)
                .where(InstagramLoginSession.id == session_id)
                .with_for_update()
            )
            if item is None or not secrets.compare_digest(
                item.launch_token_hash, hash_launch_token(token)
            ):
                raise LoginSessionError("Login link is unavailable.")
            self._expire_locked(db, item)
            if item.status != LoginSessionStatus.PENDING.value:
                raise LoginSessionError("Login link is unavailable.")
            item.status = LoginSessionStatus.ACTIVE.value
            item.consumed_at = self._now()
            item.claimed_at = self._now()
            return LoginSessionStatus.ACTIVE

    def status(self, session_id: UUID) -> LoginSessionStatus | None:
        with self._sessions.begin() as db:
            item = db.scalar(
                select(InstagramLoginSession)
                .where(InstagramLoginSession.id == session_id)
                .with_for_update()
            )
            if item is None:
                return None
            self._expire_locked(db, item)
            return LoginSessionStatus(item.status)

    def is_profile_check(self, session_id: UUID) -> bool:
        """Whether this explicitly operator-confirmed session checks a connected profile."""
        with self._sessions() as db:
            item = db.get(InstagramLoginSession, session_id)
            return bool(
                item is not None and item.prior_account_status == AccountStatus.CONNECTED.value
            )

    def cancel(self, session_id: UUID) -> LoginSessionStatus:
        with self._sessions.begin() as db:
            return self.cancel_in_transaction(db, session_id)

    def cancel_in_transaction(self, db: Session, session_id: UUID) -> LoginSessionStatus:
        item = db.scalar(
            select(InstagramLoginSession)
            .where(InstagramLoginSession.id == session_id)
            .with_for_update()
        )
        if item is None:
            raise LoginSessionError("Login session was not found.")
        self._expire_locked(db, item)
        if item.status not in {
            LoginSessionStatus.PENDING.value,
            LoginSessionStatus.ACTIVE.value,
        }:
            return LoginSessionStatus(item.status)
        item.status = LoginSessionStatus.CANCELLED.value
        item.reason_code = ReasonCode.LOGIN_CANCELLED.value
        item.closed_at = self._now()
        self._restore_account(db, item)
        return LoginSessionStatus.CANCELLED

    def complete(self, session_id: UUID) -> LoginSessionStatus:
        with self._sessions.begin() as db:
            item = db.scalar(
                select(InstagramLoginSession)
                .where(InstagramLoginSession.id == session_id)
                .with_for_update()
            )
            if item is None:
                raise LoginSessionError("Login session was not found.")
            self._expire_locked(db, item)
            if item.status != LoginSessionStatus.ACTIVE.value:
                return LoginSessionStatus(item.status)
            account = db.get(InstagramAccount, item.account_id)
            assert account is not None
            if AccountStatus(account.status) is not AccountStatus.CONNECTED:
                require_transition(
                    ACCOUNT_TRANSITIONS, AccountStatus(account.status), AccountStatus.CONNECTED
                )
                account.status = AccountStatus.CONNECTED.value
            account.reason_code = None
            account.last_connected_at = self._now()
            item.status = LoginSessionStatus.COMPLETED.value
            item.closed_at = self._now()
            return LoginSessionStatus.COMPLETED

    def _expire_locked(self, db: Session, item: InstagramLoginSession) -> None:
        expires_at = item.expires_at
        # SQLite does not round-trip timezone metadata; production PostgreSQL
        # does. Treat a test/local naive timestamp as UTC, never local time.
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if (
            item.status in {LoginSessionStatus.PENDING.value, LoginSessionStatus.ACTIVE.value}
            and expires_at <= self._now()
        ):
            item.status = LoginSessionStatus.EXPIRED.value
            item.reason_code = ReasonCode.LOGIN_EXPIRED.value
            item.closed_at = self._now()
            self._restore_account(db, item)

    def _restore_account(self, db: Session, item: InstagramLoginSession) -> None:
        account = db.get(InstagramAccount, item.account_id)
        assert account is not None
        target = AccountStatus(item.prior_account_status)
        if AccountStatus(account.status) is not target:
            require_transition(ACCOUNT_TRANSITIONS, AccountStatus(account.status), target)
            account.status = target.value
        account.reason_code = item.reason_code

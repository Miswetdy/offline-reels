"""Stage 6 control-plane checks against a real disposable PostgreSQL database.

These tests intentionally live outside the normal unit-test discovery path.  Run
them only in the disposable Stage 6 compose project with
``STAGE6_REAL_POSTGRES=1``; silently falling back to SQLite would invalidate the
locking and partial-index assertions below.
"""

# The fixture setup deliberately keeps complete database predicates visible.
# ruff: noqa: E501

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.management import (
    SESSION_COOKIE,
    _cleanup_expired_locked,
    _enforce_rate_limit,
    hash_secret,
)
from app.core.settings import get_settings
from app.db.models.instagram import (
    InstagramAccount,
    InstagramCollectionRun,
    InstagramCollectionSettings,
    InstagramLoginSession,
    ManagementDeviceSession,
    ManagementIdempotencyRecord,
    ManagementPairingChallenge,
    ManagementRateLimit,
    ManagementReserveDevice,
)
from app.db.session import create_session_factory
from app.instagram.contracts import AccountStatus
from app.main import create_app

ORIGIN = "https://localhost:18443"


@pytest.fixture(scope="module")
def sessions() -> sessionmaker[Session]:
    if os.environ.get("STAGE6_REAL_POSTGRES") != "1":
        pytest.fail("set STAGE6_REAL_POSTGRES=1; this suite requires disposable PostgreSQL")
    return create_session_factory(get_settings())


@pytest.fixture(autouse=True)
def clean_management_rows(sessions: sessionmaker[Session]) -> None:
    """Keep the disposable database deterministic without touching saved smoke data."""
    with sessions.begin() as db:
        db.execute(delete(ManagementIdempotencyRecord))
        db.execute(delete(ManagementDeviceSession))
        db.execute(delete(ManagementPairingChallenge))
        db.execute(delete(ManagementRateLimit))
        db.execute(delete(ManagementReserveDevice))
        db.execute(delete(InstagramCollectionSettings))
        db.execute(delete(InstagramLoginSession))
        db.execute(delete(InstagramCollectionRun))
        db.execute(delete(InstagramAccount))


def _new_client() -> TestClient:
    return TestClient(create_app(), base_url=ORIGIN)


def _create_challenge(
    sessions: sessionmaker[Session], *, connected: bool = False
) -> tuple[str, str]:
    account_id = uuid4()
    secret = "pairing-postgres-test-" + uuid4().hex
    with sessions.begin() as db:
        db.add(
            InstagramAccount(
                id=account_id,
                status=(AccountStatus.CONNECTED if connected else AccountStatus.DISCONNECTED),
            )
        )
        db.add(
            ManagementPairingChallenge(
                account_id=account_id,
                secret_hash=hash_secret(secret),
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        )
    return str(account_id), secret


def _pair(sessions: sessionmaker[Session], *, connected: bool = False) -> tuple[str, str, str, str]:
    account_id, secret = _create_challenge(sessions, connected=connected)
    client = _new_client()
    response = client.post(
        "/api/management/pairing/exchange",
        headers={"Origin": ORIGIN},
        json={"pairing_secret": secret},
    )
    assert response.status_code == 200
    return account_id, secret, client.cookies.get(SESSION_COOKIE), response.json()["csrf_token"]


def _pair_existing_account(sessions: sessionmaker[Session], account_id: str) -> tuple[str, str]:
    secret = "pairing-postgres-existing-account-" + uuid4().hex
    with sessions.begin() as db:
        db.add(
            ManagementPairingChallenge(
                account_id=UUID(account_id),
                secret_hash=hash_secret(secret),
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        )
    client = _new_client()
    response = client.post(
        "/api/management/pairing/exchange",
        headers={"Origin": ORIGIN},
        json={"pairing_secret": secret},
    )
    assert response.status_code == 200
    return client.cookies.get(SESSION_COOKIE), response.json()["csrf_token"]


def _mutation(cookie: str, csrf: str, key: str, target: int = 2) -> tuple[int, dict]:
    client = _new_client()
    response = client.post(
        "/api/instagram/collection-runs",
        headers={
            "Cookie": f"{SESSION_COOKIE}={cookie}",
            "Origin": ORIGIN,
            "X-CSRF-Token": csrf,
            "Idempotency-Key": key,
        },
        json={"target": target},
    )
    return response.status_code, response.json()


def test_parallel_pairing_is_single_use_and_hash_only(sessions: sessionmaker[Session]) -> None:
    _, secret = _create_challenge(sessions)

    def exchange() -> tuple[int, dict]:
        client = _new_client()
        response = client.post(
            "/api/management/pairing/exchange",
            headers={"Origin": ORIGIN},
            json={"pairing_secret": secret},
        )
        return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: exchange(), range(2)))

    assert sorted(status for status, _ in results) == [200, 401]
    csrf = next(body["csrf_token"] for status, body in results if status == 200)
    with sessions() as db:
        challenge = db.scalar(select(ManagementPairingChallenge))
        device = db.scalar(select(ManagementDeviceSession))
        assert challenge is not None and challenge.consumed_at is not None
        assert device is not None
        stored_hashes = {challenge.secret_hash, device.session_token_hash, device.csrf_token_hash}
        assert secret not in stored_hashes
        assert csrf not in stored_hashes


def test_parallel_idempotency_and_active_run_constraint(sessions: sessionmaker[Session]) -> None:
    _, _, cookie, csrf = _pair(sessions, connected=True)
    key = "same-postgres-idempotency-key"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _mutation(cookie, csrf, key), range(2)))

    assert [status for status, _ in results] == [201, 201]
    assert results[0][1]["collection_run"]["id"] == results[1][1]["collection_run"]["id"]
    changed_status, changed = _mutation(cookie, csrf, key, target=3)
    assert changed_status == 409 and changed["error"]["code"] == "idempotency_conflict"

    with sessions() as db:
        assert len(db.scalars(select(InstagramCollectionRun)).all()) == 1
        record = db.scalar(select(ManagementIdempotencyRecord))
        assert record is not None
        assert key not in record.response_json
        assert key != record.key_hash


def test_concurrent_distinct_commands_leave_one_active_run(sessions: sessionmaker[Session]) -> None:
    _, _, cookie, csrf = _pair(sessions, connected=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda number: _mutation(cookie, csrf, f"distinct-postgres-key-{number}"), range(2)
            )
        )

    assert sorted(status for status, _ in results) == [201, 409]
    conflict = next(body for status, body in results if status == 409)
    assert conflict["error"]["code"] == "active_run_exists"
    with sessions() as db:
        assert len(db.scalars(select(InstagramCollectionRun)).all()) == 1


def test_revoke_all_is_atomic_and_does_not_touch_another_account(sessions: sessionmaker[Session]) -> None:
    account_id, _, first_cookie, _ = _pair(sessions)
    account_uuid = UUID(account_id)
    _, _, second_cookie, _ = _pair(sessions)
    # Keep the second session on the same account; retain the unrelated account/session.
    with sessions.begin() as db:
        second = db.scalar(select(ManagementDeviceSession).where(ManagementDeviceSession.session_token_hash == hash_secret(second_cookie)))
        assert second is not None
        second.account_id = account_uuid
        db.flush()
        unrelated = db.scalar(select(ManagementDeviceSession).where(ManagementDeviceSession.session_token_hash == hash_secret(first_cookie)))
        assert unrelated is not None
        unrelated_account = uuid4()
        db.add(InstagramAccount(id=unrelated_account, status=AccountStatus.DISCONNECTED))
        db.add(ManagementDeviceSession(account_id=unrelated_account, session_token_hash=hash_secret("unrelated-" + uuid4().hex), csrf_token_hash=hash_secret("csrf-unrelated"), expires_at=datetime.now(UTC) + timedelta(minutes=5)))
        db.query(ManagementDeviceSession).filter(ManagementDeviceSession.account_id == account_uuid).update({ManagementDeviceSession.revoked_at: datetime.now(UTC)})
    with sessions() as db:
        assert len(db.scalars(select(ManagementDeviceSession).where(ManagementDeviceSession.account_id == account_uuid, ManagementDeviceSession.revoked_at.is_not(None))).all()) == 2
        assert len(db.scalars(select(ManagementDeviceSession).where(ManagementDeviceSession.account_id == unrelated_account, ManagementDeviceSession.revoked_at.is_(None))).all()) == 1


def test_expiry_cleanup_preserves_active_rows_and_shared_limiter(sessions: sessionmaker[Session]) -> None:
    _, _, _, _ = _pair(sessions)
    with sessions.begin() as db:
        active = db.scalar(select(ManagementDeviceSession))
        assert active is not None
        expired = ManagementDeviceSession(account_id=active.account_id, session_token_hash=hash_secret("expired-session"), csrf_token_hash=hash_secret("expired-csrf"), expires_at=datetime.now(UTC) - timedelta(seconds=1))
        db.add(expired)
        db.add(ManagementRateLimit(scope_hash=hash_secret("expired-bucket"), window_started_at=datetime.now(UTC) - timedelta(minutes=2), request_count=1))
        db.flush()
        _cleanup_expired_locked(db)
    with sessions() as db:
        assert db.get(ManagementDeviceSession, active.id) is not None
        assert db.scalar(select(ManagementDeviceSession).where(ManagementDeviceSession.session_token_hash == hash_secret("expired-session"))) is None
        assert db.scalar(select(ManagementRateLimit).where(ManagementRateLimit.scope_hash == hash_secret("expired-bucket"))) is None
    _enforce_rate_limit(sessions, "shared-test", 1)
    with pytest.raises(Exception):
        _enforce_rate_limit(sessions, "shared-test", 1)


def test_operator_cli_revoke_all_subprocess(sessions: sessionmaker[Session]) -> None:
    account_id, _, first_cookie, _ = _pair(sessions)
    account_uuid = UUID(account_id)
    _, _, second_cookie, _ = _pair(sessions)
    with sessions.begin() as db:
        second = db.scalar(select(ManagementDeviceSession).where(ManagementDeviceSession.session_token_hash == hash_secret(second_cookie)))
        assert second is not None
        second.account_id = account_uuid
        db.flush()
    result = subprocess.run([sys.executable, "-m", "app.scripts.management", "revoke-all", "--account-id", account_id], check=True, capture_output=True, text=True)
    assert "revoked" in result.stdout and first_cookie not in result.stdout and second_cookie not in result.stdout
    with sessions() as db:
        assert len(db.scalars(select(ManagementDeviceSession).where(ManagementDeviceSession.account_id == account_uuid, ManagementDeviceSession.revoked_at.is_not(None))).all()) == 2


def test_barrier_cancel_complete_race_has_one_terminal_state(sessions: sessionmaker[Session]) -> None:
    account_id, _, _, _ = _pair(sessions, connected=True)
    account_uuid = UUID(account_id)
    for number in range(20):
        with sessions.begin() as db:
            run = InstagramCollectionRun(account_id=account_uuid, trigger="manual", status="running", target_count=1)
            db.add(run)
            db.flush()
            run_id = run.id
        barrier = Barrier(2)
        def cancel() -> None:
            barrier.wait()
            with sessions.begin() as db:
                row = db.get(InstagramCollectionRun, run_id, with_for_update=True)
                if row.status == "running":
                    row.status, row.cancel_requested_at = "cancelled", datetime.now(UTC)
        def complete() -> None:
            barrier.wait()
            with sessions.begin() as db:
                row = db.get(InstagramCollectionRun, run_id, with_for_update=True)
                if row.status == "running":
                    row.status, row.completed_at = "completed", datetime.now(UTC)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda fn: fn(), (cancel, complete)))
        with sessions() as db:
            assert db.get(InstagramCollectionRun, run_id).status in {"cancelled", "completed"}


def test_concurrent_settings_updates_are_bounded_and_idempotent(sessions: sessionmaker[Session]) -> None:
    _, _, cookie, csrf = _pair(sessions)
    def update(key: str, target: int) -> tuple[int, dict]:
        client = _new_client()
        response = client.put("/api/instagram/collection-settings", json={"enabled": True, "target_reserve": target}, headers={"Cookie": f"{SESSION_COOKIE}={cookie}", "Origin": ORIGIN, "X-CSRF-Token": csrf, "Idempotency-Key": key})
        return response.status_code, response.json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda _: update("settings-same-key", 7), range(2)))
    assert [row[0] for row in rows] == [200, 200]
    assert update("settings-same-key", 8)[0] == 409


def test_concurrent_reserve_settings_and_reports_keep_one_fresh_device_row(
    sessions: sessionmaker[Session],
) -> None:
    account_id, _, first_cookie, first_csrf = _pair(sessions)
    second_cookie, second_csrf = _pair_existing_account(sessions, account_id)
    device_uuid = str(uuid4())
    now = datetime.now(UTC)
    newest_at = now + timedelta(minutes=2)
    oldest_at = now + timedelta(minutes=1)

    def mutation(
        method: str, path: str, cookie: str, csrf: str, key: str, payload: dict
    ) -> tuple[int, dict]:
        client = _new_client()
        response = client.request(
            method,
            path,
            json=payload,
            headers={
                "Cookie": f"{SESSION_COOKIE}={cookie}",
                "Origin": ORIGIN,
                "X-CSRF-Token": csrf,
                "Idempotency-Key": key,
            },
        )
        return response.status_code, response.json()

    settings_payload = {
        "device_uuid": device_uuid,
        "auto_refill_enabled": True,
        "desired_count": 20,
        "low_watermark": 8,
        "quota_threshold": 80,
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        settings_results = list(
            pool.map(
                lambda item: mutation(
                    "PUT", "/api/reserve/settings", item[0], item[1], item[2], settings_payload
                ),
                (
                    (first_cookie, first_csrf, "reserve-settings-first"),
                    (second_cookie, second_csrf, "reserve-settings-second"),
                ),
            )
        )
    assert [status for status, _ in settings_results] == [200, 200]

    def report(cookie: str, csrf: str, key: str, completed: int, reported_at: datetime) -> tuple[int, dict]:
        return mutation(
            "POST",
            "/api/reserve/reports",
            cookie,
            csrf,
            key,
            {**settings_payload, "local_completed_count": completed, "reported_at": reported_at.isoformat()},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        reports = list(
            pool.map(
                lambda item: report(*item),
                (
                    (first_cookie, first_csrf, "reserve-report-oldest", 3, oldest_at),
                    (second_cookie, second_csrf, "reserve-report-newest", 7, newest_at),
                ),
            )
        )
    assert [status for status, _ in reports] == [200, 200]
    replay = report(second_cookie, second_csrf, "reserve-report-newest", 7, newest_at)
    assert replay == reports[1]

    stale = report(first_cookie, first_csrf, "reserve-report-stale", 1, now)
    assert stale[0] == 200
    with sessions() as db:
        rows = db.scalars(select(ManagementReserveDevice)).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.account_id == UUID(account_id)
        assert str(row.device_uuid) == device_uuid
        assert row.local_completed_count == 7
        assert row.reported_at == newest_at

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.management import SESSION_COOKIE, hash_secret
from app.core.settings import Settings
from app.db.base import Base
from app.db.models.instagram import (
    InstagramAccount,
    InstagramCollectionRun,
    InstagramCollectionRunItem,
    InstagramReel,
    InstagramReelView,
    ManagementDeviceSession,
    ManagementIdempotencyRecord,
    ManagementPairingChallenge,
)
from app.db.models.video import Video
from app.instagram.contracts import AccountStatus
from app.main import create_app

ORIGIN = "https://manage.example.test"


def _client() -> tuple[TestClient, sessionmaker, str]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings.model_validate(
        {
            "database_url": "sqlite://",
            "video_cursor_secret": "x" * 32,
            "management_origin": ORIGIN,
            "login_gateway_origin": "https://login.example.test",
        }
    )
    app = create_app()
    app.state.settings = settings
    app.state.session_factory = sessions
    account_id = uuid4()
    secret = "pairing-secret-for-unit-test"
    with sessions.begin() as db:
        db.add(InstagramAccount(id=account_id, status=AccountStatus.DISCONNECTED.value))
        db.add(
            ManagementPairingChallenge(
                account_id=account_id,
                secret_hash=hash_secret(secret),
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        )
    return TestClient(app, base_url=ORIGIN), sessions, secret


def _exchange(client: TestClient, secret: str) -> str:
    result = client.post(
        "/api/management/pairing/exchange",
        headers={"Origin": ORIGIN},
        json={"pairing_secret": secret},
    )
    assert result.status_code == 200
    assert "Secure" in result.headers["set-cookie"]
    assert "HttpOnly" in result.headers["set-cookie"]
    assert "samesite=strict" in result.headers["set-cookie"].lower()
    assert SESSION_COOKIE in result.headers["set-cookie"]
    assert result.headers["cache-control"] == "no-store"
    return result.json()["csrf_token"]


def _mutation_headers(csrf: str, key: str = "idempotency-key-0001") -> dict[str, str]:
    return {"Origin": ORIGIN, "X-CSRF-Token": csrf, "Idempotency-Key": key}


def _seed_ready_reel(sessions: sessionmaker, account_id, *, title: str = "Ready Reel") -> Video:
    video = Video(
        title=title, object_key=f"videos/{uuid4()}.mp4", content_type="video/mp4", byte_size=10
    )
    with sessions.begin() as db:
        db.add(video)
        db.flush()
        reel = InstagramReel(
            shortcode=f"VIEW_{uuid4().hex[:16]}",
            canonical_url=f"https://www.instagram.com/reel/{uuid4().hex}/",
            pipeline_status="ready",
            source_object_key=f"instagram-sources/{uuid4()}.mp4",
            source_sha256="a" * 64,
            source_byte_size=10,
            video_id=video.id,
        )
        db.add(reel)
        db.flush()
        run = InstagramCollectionRun(
            account_id=account_id, trigger="manual", status="completed", target_count=1
        )
        db.add(run)
        db.flush()
        db.add(InstagramCollectionRunItem(
            run_id=run.id, reel_id=reel.id, position=1, outcome="source_committed",
            download_auth_mode="session_first",
        ))
    return video


def _view_payload(video: Video) -> dict[str, object]:
    return {
        "device_uuid": "11111111-1111-4111-8111-111111111111",
        "events": [{"video_id": str(video.id)}],
    }


def test_pairing_is_hashed_single_use_and_status_requires_cookie() -> None:
    client, sessions, secret = _client()
    denied = client.get("/api/instagram/status")
    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "unauthorized"

    csrf = _exchange(client, secret)
    assert csrf
    replay = client.post(
        "/api/management/pairing/exchange",
        headers={"Origin": ORIGIN},
        json={"pairing_secret": secret},
    )
    assert replay.status_code == 401
    with sessions() as db:
        challenge = db.scalar(select(ManagementPairingChallenge))
        device = db.scalar(select(ManagementDeviceSession))
        assert challenge is not None and challenge.secret_hash != secret and challenge.consumed_at
        assert (
            device is not None
            and device.session_token_hash != secret
            and device.csrf_token_hash != csrf
        )


def test_current_session_issues_a_fresh_no_store_csrf_capability() -> None:
    client, _, secret = _client()
    csrf = _exchange(client, secret)

    current = client.get("/api/management/session")

    assert current.status_code == 200
    assert current.headers["cache-control"] == "no-store"
    refreshed = current.json()["csrf_token"]
    assert isinstance(refreshed, str) and refreshed != csrf
    # The old browser capability cannot mutate after an application restart.
    stale = client.post(
        "/api/instagram/collection-runs",
        json={"target": 2},
        headers=_mutation_headers(csrf),
    )
    assert stale.status_code == 403
    fresh = client.post(
        "/api/instagram/collection-runs",
        json={"target": 2},
        headers=_mutation_headers(refreshed),
    )
    assert fresh.status_code == 409


def test_reserve_report_is_csrf_protected_idempotent_and_safe() -> None:
    client, sessions, secret = _client()
    csrf = _exchange(client, secret)
    payload = {
        "device_uuid": "11111111-1111-4111-8111-111111111111",
        "auto_refill_enabled": True, "local_completed_count": 3,
        "desired_count": 20, "low_watermark": 8, "quota_threshold": 80,
        "reported_at": "2026-08-12T00:00:00Z",
    }
    headers = _mutation_headers(csrf, "reserve-report-key-01")
    first = client.post("/api/reserve/reports", json=payload, headers=headers)
    second = client.post("/api/reserve/reports", json=payload, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.headers["cache-control"] == "no-store"
    assert first.json() == second.json()
    assert "device_uuid" not in first.text
    aggregate = client.get("/api/reserve/status")
    assert aggregate.status_code == 200
    assert aggregate.json()["local_completed_count"] == 3
    with sessions() as db:
        assert db.scalar(select(ManagementIdempotencyRecord)) is not None


def test_origin_csrf_and_idempotent_collection_commands() -> None:
    client, sessions, secret = _client()
    csrf = _exchange(client, secret)
    without_origin = client.post(
        "/api/instagram/collection-runs",
        json={"target": 2},
        headers={"Idempotency-Key": "abcdefgh"},
    )
    assert without_origin.status_code == 403
    assert without_origin.json()["error"]["code"] == "forbidden_origin"
    bad_csrf = client.post(
        "/api/instagram/collection-runs",
        json={"target": 2},
        headers={"Origin": ORIGIN, "X-CSRF-Token": "bad", "Idempotency-Key": "abcdefgh"},
    )
    assert bad_csrf.status_code == 403
    with sessions.begin() as db:
        account = db.scalar(select(InstagramAccount))
        assert account is not None
        account.status = AccountStatus.CONNECTED.value
    first = client.post(
        "/api/instagram/collection-runs", json={"target": 2}, headers=_mutation_headers(csrf)
    )
    second = client.post(
        "/api/instagram/collection-runs", json={"target": 2}, headers=_mutation_headers(csrf)
    )
    assert first.status_code == 201 and second.status_code == 201
    assert first.json() == second.json()
    conflict = client.post(
        "/api/instagram/collection-runs", json={"target": 3}, headers=_mutation_headers(csrf)
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
    with sessions() as db:
        assert len(db.scalars(select(InstagramCollectionRun)).all()) == 1
        row = db.scalar(select(ManagementIdempotencyRecord))
        assert row is not None and "idempotency-key-0001" not in row.response_json


def test_login_launch_is_one_time_and_cancel_is_idempotent() -> None:
    client, sessions, secret = _client()
    csrf = _exchange(client, secret)
    created = client.post(
        "/api/instagram/login-sessions", headers=_mutation_headers(csrf, "login-create-key-1")
    )
    assert created.status_code == 201
    assert created.headers["cache-control"] == "no-store"
    assert "launch_url" in created.json()
    assert created.json()["launch_url"].startswith(f"{ORIGIN}/connect/")
    launch_token = created.json()["launch_url"].split("#", maxsplit=1)[1]
    with sessions() as db:
        row = db.scalar(select(ManagementIdempotencyRecord))
        assert row is not None and launch_token not in row.response_json
    replay = client.post(
        "/api/instagram/login-sessions", headers=_mutation_headers(csrf, "login-create-key-1")
    )
    assert replay.status_code == 201
    assert "launch_url" not in replay.json()
    login_id = created.json()["login_session"]["id"]
    cancelled = client.post(
        f"/api/instagram/login-sessions/{login_id}/cancel",
        headers=_mutation_headers(csrf, "login-cancel-key-1"),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["login_session"]["status"] == "cancelled"
    again = client.post(
        f"/api/instagram/login-sessions/{login_id}/cancel",
        headers=_mutation_headers(csrf, "login-cancel-key-1"),
    )
    assert again.json() == cancelled.json()


def test_settings_status_and_revoke_current_session() -> None:
    client, _, secret = _client()
    csrf = _exchange(client, secret)
    changed = client.put(
        "/api/instagram/collection-settings",
        json={"enabled": True, "target_reserve": 7},
        headers=_mutation_headers(csrf, "settings-update-key-1"),
    )
    assert changed.status_code == 200
    assert changed.json()["scheduler_active"] is False
    status = client.get("/api/instagram/status")
    assert status.status_code == 200
    assert status.json()["auto_collection"] == {
        "enabled": True,
        "target_reserve": 7,
        "scheduler_active": False,
    }
    revoked = client.delete(
        "/api/management/session", headers=_mutation_headers(csrf, "revoke-session-key-1")
    )
    assert revoked.status_code == 200
    assert client.get("/api/instagram/status").status_code == 401


def test_view_sync_is_idempotent_and_preserves_the_first_server_timestamp() -> None:
    client, sessions, secret = _client()
    csrf = _exchange(client, secret)
    with sessions() as db:
        account = db.scalar(select(InstagramAccount))
        assert account is not None
        account_id = account.id
    video = _seed_ready_reel(sessions, account_id)
    headers = _mutation_headers(csrf, "view-sync-idempotency-01")
    first = client.post("/api/instagram/views/sync", json=_view_payload(video), headers=headers)
    replay = client.post("/api/instagram/views/sync", json=_view_payload(video), headers=headers)
    assert first.status_code == replay.status_code == 200
    assert first.headers["cache-control"] == "no-store"
    assert first.json() == replay.json() == {"confirmed_video_ids": [str(video.id)]}
    with sessions() as db:
        row = db.scalar(select(InstagramReelView))
        assert row is not None
        first_viewed_at = row.viewed_at
    second = client.post(
        "/api/instagram/views/sync",
        json=_view_payload(video),
        headers=_mutation_headers(csrf, "view-sync-idempotency-02"),
    )
    assert second.status_code == 200
    with sessions() as db:
        rows = db.scalars(select(InstagramReelView)).all()
        assert len(rows) == 1
        assert rows[0].viewed_at == first_viewed_at


def test_view_sync_and_catalog_are_account_scoped() -> None:
    client, sessions, secret = _client()
    csrf = _exchange(client, secret)
    with sessions() as db:
        account = db.scalar(select(InstagramAccount))
        device = db.scalar(select(ManagementDeviceSession))
        assert account is not None and device is not None
        first_account_id, device_id = account.id, device.id
    viewed = _seed_ready_reel(sessions, first_account_id, title="Viewed")
    available = _seed_ready_reel(sessions, first_account_id, title="Available")
    before = client.get("/api/instagram/catalog")
    assert before.status_code == 200
    assert {item["id"] for item in before.json()["items"]} == {str(viewed.id), str(available.id)}
    synced = client.post(
        "/api/instagram/views/sync",
        json=_view_payload(viewed),
        headers=_mutation_headers(csrf, "view-account-one-01"),
    )
    assert synced.status_code == 200
    after = client.get("/api/instagram/catalog")
    assert {item["id"] for item in after.json()["items"]} == {str(available.id)}
    with sessions.begin() as db:
        second = InstagramAccount(status=AccountStatus.DISCONNECTED.value)
        db.add(second)
        db.flush()
        reel = db.scalar(select(InstagramReel).where(InstagramReel.video_id == viewed.id))
        assert reel is not None
        run = InstagramCollectionRun(
            account_id=second.id, trigger="manual", status="completed", target_count=1
        )
        db.add(run)
        db.flush()
        db.add(InstagramCollectionRunItem(
            run_id=run.id, reel_id=reel.id, position=1, outcome="already_available",
            download_auth_mode=None,
        ))
        device = db.get(ManagementDeviceSession, device_id, with_for_update=True)
        assert device is not None
        device.account_id = second.id
    other_account_catalog = client.get("/api/instagram/catalog")
    assert other_account_catalog.status_code == 200
    assert {item["id"] for item in other_account_catalog.json()["items"]} == {str(viewed.id)}
    # The first account's record remains exactly one row; no URL/object key is
    # accepted or exposed by the endpoint.
    assert "object_key" not in synced.text and "canonical_url" not in synced.text

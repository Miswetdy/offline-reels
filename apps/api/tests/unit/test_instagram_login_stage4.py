from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models.instagram import InstagramAccount
from app.instagram.contracts import AccountStatus, LoginSessionStatus
from app.instagram.login_gateway import LoginGatewaySettings, create_login_gateway
from app.instagram.login_sessions import LoginSessionError, LoginSessionService, hash_launch_token


def _service(now: datetime | None = None) -> tuple[LoginSessionService, sessionmaker]:
    engine = _engine()
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    return LoginSessionService(sessions, now=(lambda: now) if now else None), sessions


def _engine():
    return create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )


def test_mobile_remote_shell_scales_width_first_without_horizontal_overflow() -> None:
    """This is an isolated layout contract; it never opens Instagram."""
    from app.instagram.login_gateway import _full_bleed_remote_viewer_page

    page = _full_bleed_remote_viewer_page(uuid4()).body.decode()
    assert "#noVNC_container" in page
    assert "height:max(100%,calc(100vw * ${REMOTE_HEIGHT} / ${REMOTE_WIDTH}))" in page
    assert (
        "Math.max(viewer.clientHeight,Math.ceil(viewer.clientWidth*REMOTE_HEIGHT/REMOTE_WIDTH))"
        in page
    )
    assert "left:0;right:0" in page
    assert "#viewer{position:absolute;inset:0" in page
    assert "maximum-scale=1,user-scalable=no" in page
    assert "#noVNC_keyboardinput{font-size:16px!important}" in page
    assert "position:fixed" in page


def test_signed_layout_preview_has_no_browser_or_instagram_content() -> None:
    from app.instagram.login_gateway import _layout_preview_page

    page = _layout_preview_page(uuid4()).body.decode()
    assert "data-layout-preview" in page
    assert "noVNC" not in page
    assert "instagram.com" not in page
    assert "left:0" in page and "right:0" in page


def test_token_is_hashed_single_use_and_active_session_is_guarded() -> None:
    service, _ = _service()
    account_id = uuid4()
    created = service.create(account_id)
    assert created.launch_token not in hash_launch_token(created.launch_token)
    assert service.activate(created.session_id, created.launch_token) is LoginSessionStatus.ACTIVE
    with pytest.raises(LoginSessionError):
        service.activate(created.session_id, created.launch_token)
    with pytest.raises(LoginSessionError):
        service.create(account_id)


def test_creation_expires_a_stale_active_session_before_active_guard() -> None:
    now = datetime(2026, 8, 9, tzinfo=UTC)
    service, _ = _service(now)
    account_id = uuid4()
    stale = service.create(account_id, timedelta(minutes=1))
    service.activate(stale.session_id, stale.launch_token)
    service._now = lambda: now + timedelta(minutes=2)  # type: ignore[method-assign]

    retry = service.create(account_id)

    assert service.status(stale.session_id) is LoginSessionStatus.EXPIRED
    assert retry.session_id != stale.session_id


def test_expiry_and_cancellation_restore_the_safe_prior_account_state() -> None:
    now = datetime(2026, 8, 9, tzinfo=UTC)
    service, sessions = _service(now)
    account_id = uuid4()
    created = service.create(account_id, timedelta(minutes=1))
    service._now = lambda: now + timedelta(minutes=2)  # type: ignore[method-assign]
    assert service.status(created.session_id) is LoginSessionStatus.EXPIRED
    with sessions() as db:
        assert db.get(InstagramAccount, account_id).status == AccountStatus.DISCONNECTED.value

    service._now = lambda: now  # type: ignore[method-assign]
    with sessions.begin() as db:
        db.get(InstagramAccount, account_id).status = AccountStatus.REAUTH_REQUIRED.value
    retry = service.create(account_id)
    assert service.cancel(retry.session_id) is LoginSessionStatus.CANCELLED
    with sessions() as db:
        assert db.get(InstagramAccount, account_id).status == AccountStatus.REAUTH_REQUIRED.value


def test_reconnect_completion_transitions_reauth_account_to_connected() -> None:
    service, sessions = _service()
    account_id = uuid4()
    with sessions.begin() as db:
        db.add(InstagramAccount(id=account_id, status=AccountStatus.REAUTH_REQUIRED.value))
    created = service.create(account_id)
    service.activate(created.session_id, created.launch_token)
    assert service.complete(created.session_id) is LoginSessionStatus.COMPLETED
    with sessions() as db:
        assert db.get(InstagramAccount, account_id).status == AccountStatus.CONNECTED.value


def test_explicit_connected_profile_check_preserves_connected_account_state() -> None:
    service, sessions = _service()
    account_id = uuid4()
    with sessions.begin() as db:
        db.add(InstagramAccount(id=account_id, status=AccountStatus.CONNECTED.value))
    with pytest.raises(LoginSessionError):
        service.create(account_id)
    created = service.create(account_id, allow_connected_profile_check=True)
    service.activate(created.session_id, created.launch_token)
    assert service.complete(created.session_id) is LoginSessionStatus.COMPLETED
    with sessions() as db:
        assert db.get(InstagramAccount, account_id).status == AccountStatus.CONNECTED.value


class _ConnectedBrowser:
    async def readiness(self) -> str:
        return "connected"

    async def close(self) -> None:
        return None

    async def open_login(self) -> bool:
        return True

    async def verify_profile(self) -> bool:
        return True


class _VerifyingBrowser(_ConnectedBrowser):
    def __init__(self) -> None:
        self.states = iter(("verifying", "connected"))
        self.profile_checks = 0

    async def readiness(self) -> str:
        return next(self.states)

    async def verify_profile(self) -> bool:
        self.profile_checks += 1
        return True


class _StillVerifyingBrowser(_ConnectedBrowser):
    def __init__(self) -> None:
        self.profile_checks = 0

    async def readiness(self) -> str:
        return "verifying"

    async def verify_profile(self) -> bool:
        self.profile_checks += 1
        return True


def test_gateway_requires_host_cookie_and_origin_and_closes_on_connected() -> None:
    engine = _engine()
    Base.metadata.create_all(engine)
    settings = LoginGatewaySettings.model_validate(
        {
            "DATABASE_URL": "sqlite://",
            "LOGIN_GATEWAY_ORIGIN": "https://login.example.test",
            "LOGIN_GATEWAY_SESSION_SECRET": "a" * 32,
            "LOGIN_BROWSER_CONTROL_SECRET": "b" * 32,
        }
    )
    app = create_login_gateway(settings, _ConnectedBrowser())
    app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    app.state.login_sessions = LoginSessionService(app.state.session_factory)
    created = app.state.login_sessions.create(uuid4())
    client = TestClient(app, base_url="https://login.example.test")
    page = client.get(f"/connect/{created.session_id}")
    assert page.status_code == 200
    assert created.launch_token not in page.text
    assert "launch_token" in page.text
    assert app.state.login_sessions.status(created.session_id) is LoginSessionStatus.PENDING
    assert page.headers["content-security-policy"].find("frame-ancestors 'none'") >= 0
    activated = client.post(
        f"/connect/{created.session_id}/activate",
        headers={"origin": "https://login.example.test"},
        json={"launch_token": created.launch_token},
    )
    assert activated.status_code == 204
    remote = client.get(f"/remote/{created.session_id}")
    assert "vnc.html" in remote.text
    assert "noVNC_keyboard_button" in remote.text
    assert "resize=scale" in remote.text
    opened = client.post(
        f"/remote/{created.session_id}/open-login",
        headers={"origin": "https://login.example.test"},
    )
    assert opened.status_code == 202
    state = client.get(f"/remote/{created.session_id}/state")
    assert state.json() == {"state": "completed"}
    denied = client.get(f"/remote/{created.session_id}/state", headers={"host": "evil.example"})
    assert denied.status_code == 400


def test_connected_profile_check_hides_remote_browser_until_reauth_is_required() -> None:
    engine = _engine()
    Base.metadata.create_all(engine)
    settings = LoginGatewaySettings.model_validate(
        {
            "DATABASE_URL": "sqlite://",
            "LOGIN_GATEWAY_ORIGIN": "https://login.example.test",
            "LOGIN_GATEWAY_SESSION_SECRET": "a" * 32,
            "LOGIN_BROWSER_CONTROL_SECRET": "b" * 32,
        }
    )
    app = create_login_gateway(settings, _ConnectedBrowser())
    app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    app.state.login_sessions = LoginSessionService(app.state.session_factory)
    account_id = uuid4()
    with app.state.session_factory.begin() as db:
        db.add(InstagramAccount(id=account_id, status=AccountStatus.CONNECTED.value))
    created = app.state.login_sessions.create(account_id, allow_connected_profile_check=True)
    client = TestClient(app, base_url="https://login.example.test")
    assert client.post(
        f"/connect/{created.session_id}/activate",
        headers={"origin": "https://login.example.test"},
        json={"launch_token": created.launch_token},
    ).status_code == 204
    page = client.get(f"/remote/{created.session_id}")
    assert "Проверяем подключение" in page.text
    assert "vnc.html" not in page.text
    assert client.post(
        f"/remote/{created.session_id}/verify-profile",
        headers={"origin": "https://login.example.test"},
    ).status_code == 202
    assert client.get(f"/remote/{created.session_id}/state").json() == {"state": "completed"}


def test_connected_profile_inspection_viewer_does_not_poll_or_complete() -> None:
    engine = _engine()
    Base.metadata.create_all(engine)
    settings = LoginGatewaySettings.model_validate(
        {
            "DATABASE_URL": "sqlite://",
            "LOGIN_GATEWAY_ORIGIN": "https://login.example.test",
            "LOGIN_GATEWAY_SESSION_SECRET": "a" * 32,
            "LOGIN_BROWSER_CONTROL_SECRET": "b" * 32,
        }
    )
    app = create_login_gateway(settings, _ConnectedBrowser())
    app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    app.state.login_sessions = LoginSessionService(app.state.session_factory)
    account_id = uuid4()
    with app.state.session_factory.begin() as db:
        db.add(InstagramAccount(id=account_id, status=AccountStatus.CONNECTED.value))
    created = app.state.login_sessions.create(account_id, allow_connected_profile_check=True)
    client = TestClient(app, base_url="https://login.example.test")
    start = client.get(f"/connect/{created.session_id}?inspect=1")
    assert "const inspection=true" in start.text
    assert client.post(
        f"/connect/{created.session_id}/activate",
        headers={"origin": "https://login.example.test"},
        json={"launch_token": created.launch_token},
    ).status_code == 204
    viewer = client.get(f"/remote/{created.session_id}/interactive")
    assert "new RFB" in viewer.text
    assert "addEventListener('connect'" in viewer.text
    assert "addEventListener('disconnect'" in viewer.text
    assert "setInterval(poll,5000)" not in viewer.text
    assert app.state.login_sessions.status(created.session_id) is LoginSessionStatus.ACTIVE


def test_post_login_verification_hides_remote_view_before_reels_check() -> None:
    engine = _engine()
    Base.metadata.create_all(engine)
    settings = LoginGatewaySettings.model_validate(
        {
            "DATABASE_URL": "sqlite://",
            "LOGIN_GATEWAY_ORIGIN": "https://login.example.test",
            "LOGIN_GATEWAY_SESSION_SECRET": "a" * 32,
            "LOGIN_BROWSER_CONTROL_SECRET": "b" * 32,
        }
    )
    browser = _VerifyingBrowser()
    app = create_login_gateway(settings, browser)
    app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    app.state.login_sessions = LoginSessionService(app.state.session_factory)
    created = app.state.login_sessions.create(uuid4())
    client = TestClient(app, base_url="https://login.example.test")
    assert client.post(
        f"/connect/{created.session_id}/activate",
        headers={"origin": "https://login.example.test"},
        json={"launch_token": created.launch_token},
    ).status_code == 204
    remote = client.get(f"/remote/{created.session_id}")
    assert "Проверяем подключение" in remote.text
    assert "showChecking" in remote.text
    first = client.get(f"/remote/{created.session_id}/state")
    assert first.json() == {"state": "verifying"}
    assert browser.profile_checks == 1
    assert client.get(f"/remote/{created.session_id}/state").json() == {"state": "completed"}


def test_profile_verification_navigation_is_not_repeated_while_loading() -> None:
    engine = _engine()
    Base.metadata.create_all(engine)
    settings = LoginGatewaySettings.model_validate(
        {
            "DATABASE_URL": "sqlite://",
            "LOGIN_GATEWAY_ORIGIN": "https://login.example.test",
            "LOGIN_GATEWAY_SESSION_SECRET": "a" * 32,
            "LOGIN_BROWSER_CONTROL_SECRET": "b" * 32,
        }
    )
    browser = _StillVerifyingBrowser()
    app = create_login_gateway(settings, browser)
    app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    app.state.login_sessions = LoginSessionService(app.state.session_factory)
    created = app.state.login_sessions.create(uuid4())
    client = TestClient(app, base_url="https://login.example.test")
    assert client.post(
        f"/connect/{created.session_id}/activate",
        headers={"origin": "https://login.example.test"},
        json={"launch_token": created.launch_token},
    ).status_code == 204

    assert client.get(f"/remote/{created.session_id}/state").json() == {"state": "verifying"}
    assert client.get(f"/remote/{created.session_id}/state").json() == {"state": "verifying"}
    assert browser.profile_checks == 1


def test_gateway_rejects_reused_link_and_bad_websocket_origin() -> None:
    settings = LoginGatewaySettings.model_validate(
        {
            "DATABASE_URL": "sqlite://",
            "LOGIN_GATEWAY_ORIGIN": "https://login.example.test",
            "LOGIN_GATEWAY_SESSION_SECRET": "a" * 32,
            "LOGIN_BROWSER_CONTROL_SECRET": "b" * 32,
        }
    )
    app = create_login_gateway(settings, _ConnectedBrowser())
    engine = _engine()
    Base.metadata.create_all(engine)
    app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    app.state.login_sessions = LoginSessionService(app.state.session_factory)
    created = app.state.login_sessions.create(uuid4())
    client = TestClient(app, base_url="https://login.example.test")
    assert client.get(f"/connect/{created.session_id}").status_code == 200
    assert client.post(
        f"/connect/{created.session_id}/activate",
        headers={"origin": "https://login.example.test"},
        json={"launch_token": created.launch_token},
    ).status_code == 204
    fresh = TestClient(app, base_url="https://login.example.test")
    assert fresh.get(f"/connect/{created.session_id}").status_code == 200
    assert fresh.post(
        f"/connect/{created.session_id}/activate",
        headers={"origin": "https://login.example.test"},
        json={"launch_token": created.launch_token},
    ).status_code == 409
    with pytest.raises(Exception):
        with fresh.websocket_connect(
            f"/remote/{created.session_id}/websockify", headers={"origin": "https://evil.example"}
        ):
            pass


def test_gateway_refuses_a_plain_http_public_origin() -> None:
    with pytest.raises(ValueError):
        LoginGatewaySettings.model_validate(
            {
                "DATABASE_URL": "sqlite://",
                "LOGIN_GATEWAY_ORIGIN": "http://login.example.test",
                "LOGIN_GATEWAY_SESSION_SECRET": "a" * 32,
                "LOGIN_BROWSER_CONTROL_SECRET": "b" * 32,
            }
        )

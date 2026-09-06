from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.instagram.collector.runtime.handoff_state import HandoffStateStore
from app.instagram.login_gateway import LoginGatewaySettings, _sign_session, _websocket_allowed


def test_handoff_is_single_use_and_expiry_fails_closed(tmp_path) -> None:
    now = [datetime(2026, 1, 1, tzinfo=UTC)]
    store = HandoffStateStore(tmp_path, now=lambda: now[0])
    created = store.create(ttl=timedelta(seconds=1))
    assert store.state(created.session_id) == "pending"
    assert store.activate(created.session_id, "wrong") == "unavailable"
    assert store.activate(created.session_id, created.launch_token) == "active"
    assert store.activate(created.session_id, created.launch_token) == "unavailable"
    now[0] += timedelta(seconds=2)
    assert store.state(created.session_id) == "expired"


def test_handoff_confirmation_and_cancellation_are_terminal(tmp_path) -> None:
    store = HandoffStateStore(tmp_path)
    created = store.create()
    assert store.activate(created.session_id, created.launch_token) == "active"
    assert store.resolve(created.session_id, confirmed=True) == "confirmed"
    assert store.resolve(created.session_id, confirmed=False) == "confirmed"


def test_handoff_websocket_uses_its_own_signed_cookie_name() -> None:
    session_id = uuid4()
    settings = LoginGatewaySettings.model_validate(
        {
            "DATABASE_URL": "sqlite://",
            "LOGIN_GATEWAY_ORIGIN": "https://login.example.test",
            "LOGIN_GATEWAY_SESSION_SECRET": "a" * 32,
            "LOGIN_BROWSER_CONTROL_SECRET": "b" * 32,
        }
    )
    websocket = SimpleNamespace(
        headers={"host": "login.example.test", "origin": "https://login.example.test"},
        cookies={"handoff_gateway_session": _sign_session(session_id, settings)},
    )

    assert _websocket_allowed(
        websocket, session_id, settings, cookie_name="handoff_gateway_session"
    )
    assert not _websocket_allowed(websocket, session_id, settings)

from datetime import UTC, datetime, timedelta

from app.instagram.collector.runtime.handoff_state import HandoffStateStore


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

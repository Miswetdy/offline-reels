from uuid import uuid4

from app.scripts import management


class _Session:
    def __init__(self) -> None:
        self.added: list[object] = []

    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get(self, *_: object) -> object:
        return object()

    def add(self, item: object) -> None:
        self.added.append(item)

    def flush(self) -> None:
        return None


class _Sessions:
    def __init__(self) -> None:
        self.session = _Session()

    def begin(self) -> _Session:
        return self.session


def test_create_pairing_accepts_numeric_ttl_argument(monkeypatch, capsys) -> None:
    sessions = _Sessions()
    monkeypatch.setattr(management, "create_session_factory", lambda _: sessions)
    monkeypatch.setattr(management, "get_settings", lambda: object())

    assert management.main([
        "create-pairing",
        "--account-id",
        str(uuid4()),
        "--ttl-minutes",
        "10",
    ]) == 0

    assert len(sessions.session.added) == 1
    assert "PAIRING_SECRET=" in capsys.readouterr().out

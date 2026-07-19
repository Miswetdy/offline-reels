from fastapi.testclient import TestClient

from app.api import health
from app.main import app

client = TestClient(app)


def test_live_does_not_check_dependencies(monkeypatch) -> None:
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("dependency check must not run for /health/live")

    monkeypatch.setattr(health, "check_postgres", fail_if_called)

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_allows_only_configured_frontend_origin() -> None:
    response = client.options(
        "/health/live",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"

    rejected = client.options(
        "/health/live",
        headers={
            "Origin": "http://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers


def test_ready_checks_postgres_and_redis(monkeypatch) -> None:
    postgres_calls: list[object] = []
    redis_calls: list[object] = []

    def postgres_check(settings) -> None:
        postgres_calls.append(settings)

    async def redis_check(settings) -> None:
        redis_calls.append(settings)

    monkeypatch.setattr(health, "check_postgres", postgres_check)
    monkeypatch.setattr(health, "check_redis", redis_check)

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(postgres_calls) == 1
    assert len(redis_calls) == 1


def test_ready_returns_503_when_postgres_is_unavailable(monkeypatch) -> None:
    def postgres_check(_settings) -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(health, "check_postgres", postgres_check)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": {"status": "unavailable"}}


def test_minio_diagnostic_is_independent_from_readiness(monkeypatch) -> None:
    def minio_check(_settings) -> None:
        raise RuntimeError("minio unavailable")

    monkeypatch.setattr(health, "check_minio", minio_check)

    response = client.get("/health/minio")

    assert response.status_code == 503
    assert response.json() == {"detail": {"status": "unavailable"}}

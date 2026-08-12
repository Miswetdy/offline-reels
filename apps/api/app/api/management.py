"""Protected PostgreSQL-only control plane for the Instagram Collector.

This module deliberately imports neither the Collector runtime nor any browser,
downloader, ffmpeg or normalizer worker implementation.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import Settings
from app.db.models.instagram import (
    InstagramAccount,
    InstagramCollectionRun,
    InstagramCollectionSettings,
    InstagramLoginSession,
    InstagramNormalizationJob,
    InstagramReel,
    ManagementDeviceSession,
    ManagementIdempotencyRecord,
    ManagementPairingChallenge,
    ManagementRateLimit,
)
from app.instagram.contracts import (
    AccountStatus,
    CollectionRunStatus,
    CollectionTrigger,
    ReelPipelineStatus,
)
from app.instagram.login_sessions import LoginSessionError, LoginSessionService

router = APIRouter(prefix="/api", tags=["management"])
SESSION_COOKIE = "__Host-offline-reels-management"
CSRF_HEADER = "X-CSRF-Token"
IDEMPOTENCY_TTL = timedelta(hours=24)
MAX_KEY_LENGTH = 128


class ManagementError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


class PairingExchange(BaseModel):
    pairing_secret: str = Field(min_length=16, max_length=256)


class TargetRequest(BaseModel):
    target: int = Field(ge=1, le=10)


class SettingsRequest(BaseModel):
    enabled: bool
    target_reserve: int = Field(ge=1, le=10)


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _is_expired(value: datetime, now: datetime | None = None) -> bool:
    """SQLite fixtures lose timezone metadata; PostgreSQL does not."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= (now or _now())


def _origin(settings: Settings) -> str:
    return str(settings.management_origin).rstrip("/")


def _expected_host(settings: Settings) -> str:
    url = settings.management_origin
    default_port = 443 if url.scheme == "https" else 80
    return url.host if url.port in {None, default_port} else f"{url.host}:{url.port}"


def _require_host(request: Request, settings: Settings) -> None:
    if request.headers.get("host", "").lower() != _expected_host(settings).lower():
        raise ManagementError(403, "forbidden_origin", "Недопустимый источник запроса.")


def _require_origin(request: Request, settings: Settings) -> None:
    _require_host(request, settings)
    if request.headers.get("origin") != _origin(settings):
        raise ManagementError(403, "forbidden_origin", "Недопустимый источник запроса.")


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_sessions(request: Request) -> sessionmaker[Session]:
    return request.app.state.session_factory


def _safe_session(session: ManagementDeviceSession) -> dict[str, Any]:
    return {
        "session_id": str(session.id),
        "device_id": str(session.device_id),
        "expires_at": session.expires_at.isoformat(),
    }


def _serialize_login(item: InstagramLoginSession) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "status": item.status,
        "expires_at": item.expires_at.isoformat(),
        "reason_code": item.reason_code,
    }


def _serialize_run(item: InstagramCollectionRun) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "status": item.status,
        "target": item.target_count,
        "source_committed_count": item.source_committed_count,
        "already_available_count": item.already_available_count,
        "failed_count": item.failed_count,
        "cancel_requested": item.cancel_requested_at is not None,
        "reason_code": item.stop_reason_code,
    }


def _cleanup_expired_locked(db: Session, now: datetime | None = None) -> None:
    """Idempotent expiry cleanup performed inside ordinary control-plane transactions."""
    current = now or _now()
    db.execute(
        delete(ManagementIdempotencyRecord).where(ManagementIdempotencyRecord.expires_at <= current)
    )
    db.execute(
        delete(ManagementPairingChallenge).where(ManagementPairingChallenge.expires_at <= current)
    )
    db.execute(delete(ManagementDeviceSession).where(ManagementDeviceSession.expires_at <= current))
    db.execute(
        delete(ManagementRateLimit).where(
            ManagementRateLimit.window_started_at <= current - timedelta(minutes=1)
        )
    )


def _get_current_session(
    request: Request, settings: Settings, sessions: sessionmaker[Session]
) -> ManagementDeviceSession:
    _require_host(request, settings)
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise ManagementError(401, "unauthorized", "Требуется привязка устройства.")
    with sessions.begin() as db:
        _cleanup_expired_locked(db)
        item = db.scalar(
            select(ManagementDeviceSession).where(
                ManagementDeviceSession.session_token_hash == hash_secret(token)
            )
        )
        if item is None or item.revoked_at is not None or _is_expired(item.expires_at):
            raise ManagementError(401, "session_expired", "Сессия управления недоступна.")
        db.expunge(item)
        return item


def require_management_session(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    sessions: Annotated[sessionmaker[Session], Depends(get_sessions)],
) -> ManagementDeviceSession:
    return _get_current_session(request, settings, sessions)


def require_mutation(
    request: Request,
    session: Annotated[ManagementDeviceSession, Depends(require_management_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    sessions: Annotated[sessionmaker[Session], Depends(get_sessions)],
) -> ManagementDeviceSession:
    _require_origin(request, settings)
    _enforce_rate_limit(sessions, f"mutation:{session.id}", 60)
    csrf = request.headers.get(CSRF_HEADER)
    if not csrf or not secrets.compare_digest(hash_secret(csrf), session.csrf_token_hash):
        raise ManagementError(403, "csrf_invalid", "Проверка безопасности запроса не пройдена.")
    return session


def _idempotency_key(value: str | None) -> str:
    if value is None or not 8 <= len(value) <= MAX_KEY_LENGTH or not value.isascii():
        raise ManagementError(400, "idempotency_required", "Нужен корректный ключ идемпотентности.")
    return value


def _enforce_rate_limit(sessions: sessionmaker[Session], scope: str, limit: int) -> None:
    """Shared fixed-window limiter; scope is a non-reversible hash, never IP/UA."""
    scope_hash = hash_secret(scope)
    # Two requests can both observe an empty scope.  A unique-insert collision
    # is not abuse: retry once so the losing transaction locks and increments
    # the row committed by the winner instead of returning a false 429.
    for attempt in range(2):
        try:
            with sessions.begin() as db:
                # PostgreSQL instances must share a clock for a fixed window.
                now = (
                    db.scalar(select(func.now()))
                    if db.bind and db.bind.dialect.name == "postgresql"
                    else _now()
                )
                assert now is not None
                item = db.scalar(
                    select(ManagementRateLimit)
                    .where(ManagementRateLimit.scope_hash == scope_hash)
                    .with_for_update()
                )
                if item is None:
                    db.add(
                        ManagementRateLimit(
                            scope_hash=scope_hash, window_started_at=now, request_count=1
                        )
                    )
                    return
                started = item.window_started_at
                if started.tzinfo is None:
                    started = started.replace(tzinfo=UTC)
                if started + timedelta(minutes=1) <= now:
                    item.window_started_at = now
                    item.request_count = 1
                    return
                if item.request_count >= limit:
                    raise ManagementError(
                        429, "rate_limited", "Слишком много запросов. Повторите позже."
                    )
                item.request_count += 1
                return
        except IntegrityError:
            if attempt == 0:
                continue
            raise ManagementError(
                429, "rate_limited", "Слишком много запросов. Повторите позже."
            ) from None


def _idempotent(
    sessions: sessionmaker[Session],
    session: ManagementDeviceSession,
    operation: str,
    key: str | None,
    body: BaseModel,
    action: Callable[[Session], tuple[int, dict[str, Any]]],
) -> tuple[int, dict[str, Any], bool]:
    raw_key = _idempotency_key(key)
    key_hash = hash_secret(raw_key)
    fingerprint = hash_secret(
        json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    )
    now = _now()
    try:
        with sessions.begin() as db:
            _cleanup_expired_locked(db, now)
            # A row lock cannot protect a key that does not exist yet.  On
            # PostgreSQL, serialize the first writer for this exact
            # session/operation/key tuple before inspecting or creating it.
            # The lock is transaction-scoped and its numeric key is derived
            # from hashes only; no idempotency secret reaches PostgreSQL.
            if db.bind is not None and db.bind.dialect.name == "postgresql":
                lock_material = f"{session.id}:{operation}:{key_hash}".encode("ascii")
                lock_id = int.from_bytes(hashlib.sha256(lock_material).digest()[:8], signed=True)
                db.execute(select(func.pg_advisory_xact_lock(lock_id)))
            existing = db.scalar(
                select(ManagementIdempotencyRecord)
                .where(
                    ManagementIdempotencyRecord.session_id == session.id,
                    ManagementIdempotencyRecord.operation == operation,
                    ManagementIdempotencyRecord.key_hash == key_hash,
                )
                .with_for_update()
            )
            if existing is not None:
                if not secrets.compare_digest(existing.request_fingerprint, fingerprint):
                    raise ManagementError(
                        409, "idempotency_conflict", "Ключ использован с другим запросом."
                    )
                return existing.response_status, json.loads(existing.response_json), True
            response_status, result = action(db)
            persisted_result = {
                key: value for key, value in result.items() if key != "_launch_token"
            }
            db.add(
                ManagementIdempotencyRecord(
                    session_id=session.id,
                    operation=operation,
                    key_hash=key_hash,
                    request_fingerprint=fingerprint,
                    response_status=response_status,
                    response_json=json.dumps(
                        persisted_result, sort_keys=True, separators=(",", ":")
                    ),
                    expires_at=now + IDEMPOTENCY_TTL,
                )
            )
            return response_status, result, False
    except IntegrityError:
        with sessions() as db:
            existing = db.scalar(
                select(ManagementIdempotencyRecord).where(
                    ManagementIdempotencyRecord.session_id == session.id,
                    ManagementIdempotencyRecord.operation == operation,
                    ManagementIdempotencyRecord.key_hash == key_hash,
                )
            )
            if existing is not None and secrets.compare_digest(
                existing.request_fingerprint, fingerprint
            ):
                return existing.response_status, json.loads(existing.response_json), True
        raise ManagementError(503, "service_unavailable", "Сервис временно недоступен.") from None


@router.post("/management/pairing/exchange")
def exchange_pairing(
    payload: PairingExchange,
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    sessions: Annotated[sessionmaker[Session], Depends(get_sessions)],
) -> dict[str, Any]:
    _require_origin(request, settings)
    _enforce_rate_limit(sessions, "pairing", 10)
    now = _now()
    with sessions.begin() as db:
        challenge = db.scalar(
            select(ManagementPairingChallenge)
            .where(ManagementPairingChallenge.secret_hash == hash_secret(payload.pairing_secret))
            .with_for_update()
        )
        if (
            challenge is None
            or challenge.consumed_at is not None
            or _is_expired(challenge.expires_at, now)
        ):
            raise ManagementError(401, "pairing_unavailable", "Код привязки недоступен.")
        challenge.consumed_at = now
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        device = ManagementDeviceSession(
            account_id=challenge.account_id,
            session_token_hash=hash_secret(token),
            csrf_token_hash=hash_secret(csrf),
            expires_at=now + timedelta(minutes=settings.management_session_ttl_minutes),
        )
        db.add(device)
        db.flush()
        safe = _safe_session(device)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        secure=True,
        httponly=True,
        samesite="strict",
        path="/",
        max_age=settings.management_session_ttl_minutes * 60,
    )
    response.headers["Cache-Control"] = "no-store"
    return {"session": safe, "csrf_token": csrf}


@router.get("/management/session")
def current_session(
    response: Response,
    session: Annotated[ManagementDeviceSession, Depends(require_management_session)],
    sessions: Annotated[sessionmaker[Session], Depends(get_sessions)],
) -> dict[str, Any]:
    # The management cookie is HttpOnly, so a freshly opened PWA needs a new
    # CSRF capability before it can make protected mutations.  Only its hash
    # is durable; the plaintext is sent once over the already authenticated,
    # same-origin HTTPS request and is never logged or persisted by the API.
    csrf = secrets.token_urlsafe(24)
    with sessions.begin() as db:
        current = db.get(ManagementDeviceSession, session.id, with_for_update=True)
        if current is None or current.revoked_at is not None or _is_expired(current.expires_at):
            raise ManagementError(401, "session_expired", "Сессия управления недоступна.")
        current.csrf_token_hash = hash_secret(csrf)
    response.headers["Cache-Control"] = "no-store"
    return {"session": _safe_session(session), "csrf_token": csrf}


@router.delete("/management/session")
def revoke_current_session(
    request: Request,
    response: Response,
    session: Annotated[ManagementDeviceSession, Depends(require_mutation)],
    settings: Annotated[Settings, Depends(get_settings)],
    sessions: Annotated[sessionmaker[Session], Depends(get_sessions)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    status_code, result, _ = _idempotent(
        sessions,
        session,
        "revoke_current_session",
        idempotency_key,
        SettingsRequest(enabled=False, target_reserve=1),
        lambda db: _revoke_locked(db, session.id),
    )
    del status_code, settings
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return result


def _revoke_locked(db: Session, session_id: UUID) -> tuple[int, dict[str, Any]]:
    item = db.get(ManagementDeviceSession, session_id, with_for_update=True)
    if item is not None and item.revoked_at is None:
        item.revoked_at = _now()
    return 200, {"revoked": True}


@router.get("/instagram/status")
def instagram_status(
    session: Annotated[ManagementDeviceSession, Depends(require_management_session)],
    sessions: Annotated[sessionmaker[Session], Depends(get_sessions)],
) -> dict[str, Any]:
    with sessions() as db:
        account = db.get(InstagramAccount, session.account_id)
        active_login = db.scalar(
            select(InstagramLoginSession).where(
                InstagramLoginSession.account_id == session.account_id,
                InstagramLoginSession.status.in_(("pending", "active")),
            )
        )
        active_run = db.scalar(
            select(InstagramCollectionRun).where(
                InstagramCollectionRun.account_id == session.account_id,
                InstagramCollectionRun.status.in_(("queued", "running")),
            )
        )

        def count_jobs(status: str) -> int:
            return int(
                db.scalar(
                    select(func.count())
                    .select_from(InstagramNormalizationJob)
                    .where(InstagramNormalizationJob.status == status)
                )
                or 0
            )

        settings = db.get(InstagramCollectionSettings, session.account_id)
        ready = int(
            db.scalar(
                select(func.count())
                .select_from(InstagramReel)
                .where(InstagramReel.pipeline_status == ReelPipelineStatus.READY.value)
            )
            or 0
        )
        cleanup = int(
            db.scalar(
                select(func.count())
                .select_from(InstagramReel)
                .where(InstagramReel.source_cleanup_pending.is_(True))
            )
            or 0
        )
        return {
            "connection_status": account.status if account else AccountStatus.DISCONNECTED.value,
            "reconnect_required": bool(
                account and account.status == AccountStatus.REAUTH_REQUIRED.value
            ),
            "reason_code": account.reason_code if account else None,
            "active_login": _serialize_login(active_login) if active_login else None,
            "active_collection": _serialize_run(active_run) if active_run else None,
            "normalization": {
                "pending": count_jobs("pending"),
                "running": count_jobs("running"),
                "completed": count_jobs("completed"),
                "failed": count_jobs("failed"),
                "cleanup_pending": cleanup,
            },
            "ready_count": ready,
            "auto_collection": {
                "enabled": settings.enabled if settings else False,
                "target_reserve": settings.target_reserve if settings else 5,
                "scheduler_active": False,
            },
        }


@router.post("/instagram/login-sessions")
def create_login_session(
    request: Request,
    response: Response,
    session: Annotated[ManagementDeviceSession, Depends(require_mutation)],
    sessions: Annotated[sessionmaker[Session], Depends(get_sessions)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    empty = TargetRequest(target=1)

    def action(db: Session) -> tuple[int, dict[str, Any]]:
        service = LoginSessionService(sessions)
        try:
            created = service.create_in_transaction(db, session.account_id)
        except LoginSessionError as error:
            message = str(error)
            if "active" in message.lower():
                raise ManagementError(
                    409, "active_login_exists", "Уже есть активная сессия входа."
                ) from None
            raise ManagementError(
                409, "reauth_required", "Сейчас нельзя начать вход в Instagram."
            ) from None
        return 201, {
            "login_session": {
                "id": str(created.session_id),
                "status": "pending",
                "expires_at": created.expires_at.isoformat(),
                "reason_code": None,
            },
            "_launch_token": created.launch_token,
        }

    status_code, result, replay = _idempotent(
        sessions, session, "create_login", idempotency_key, empty, action
    )
    response.headers["Cache-Control"] = "no-store"
    result = dict(result)
    token = result.pop("_launch_token", None)
    if token is not None and not replay:
        # The browser accepts a launch only on the paired management origin.
        # Deployment routes this fixed path to the isolated Stage 4 gateway;
        # a separate gateway origin or caller-controlled return URL is never
        # a capability-bearing navigation target.
        gateway = _origin(request.app.state.settings)
        result["launch_url"] = f"{gateway}/connect/{result['login_session']['id']}#{token}"
    response.status_code = status_code
    return result


@router.get("/instagram/login-sessions/{login_session_id}")
def login_session_status(
    login_session_id: UUID,
    session: Annotated[ManagementDeviceSession, Depends(require_management_session)],
    sessions: Annotated[sessionmaker[Session], Depends(get_sessions)],
) -> dict[str, Any]:
    with sessions() as db:
        item = db.get(InstagramLoginSession, login_session_id)
        if item is None or item.account_id != session.account_id:
            raise ManagementError(404, "login_not_found", "Сессия входа не найдена.")
        return {"login_session": _serialize_login(item)}


@router.post("/instagram/login-sessions/{login_session_id}/cancel")
def cancel_login_session(
    login_session_id: UUID,
    request: Request,
    response: Response,
    session: Annotated[ManagementDeviceSession, Depends(require_mutation)],
    sessions: Annotated[sessionmaker[Session], Depends(get_sessions)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    def action(db: Session) -> tuple[int, dict[str, Any]]:
        item = db.get(InstagramLoginSession, login_session_id, with_for_update=True)
        if item is None or item.account_id != session.account_id:
            raise ManagementError(404, "login_not_found", "Сессия входа не найдена.")
        try:
            current = LoginSessionService(sessions).cancel_in_transaction(db, login_session_id)
        except LoginSessionError:
            raise ManagementError(404, "login_not_found", "Сессия входа не найдена.") from None
        return 200, {"login_session": {**_serialize_login(item), "status": current.value}}

    status_code, result, _ = _idempotent(
        sessions, session, "cancel_login", idempotency_key, TargetRequest(target=1), action
    )
    response.status_code = status_code
    return result


@router.post("/instagram/collection-runs")
def create_collection_run(
    payload: TargetRequest,
    response: Response,
    session: Annotated[ManagementDeviceSession, Depends(require_mutation)],
    sessions: Annotated[sessionmaker[Session], Depends(get_sessions)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    def action(db: Session) -> tuple[int, dict[str, Any]]:
        account = db.get(InstagramAccount, session.account_id, with_for_update=True)
        if account is None or account.status != AccountStatus.CONNECTED.value:
            code = (
                "reauth_required"
                if account and account.status == AccountStatus.REAUTH_REQUIRED.value
                else "account_not_connected"
            )
            raise ManagementError(409, code, "Instagram не подключён.")
        active = db.scalar(
            select(InstagramCollectionRun)
            .where(
                InstagramCollectionRun.account_id == session.account_id,
                InstagramCollectionRun.status.in_(("queued", "running")),
            )
            .with_for_update()
        )
        if active is not None:
            raise ManagementError(409, "active_run_exists", "Уже выполняется сбор.")
        item = InstagramCollectionRun(
            account_id=session.account_id,
            trigger=CollectionTrigger.MANUAL.value,
            status=CollectionRunStatus.QUEUED.value,
            target_count=payload.target,
        )
        db.add(item)
        db.flush()
        return 201, {"collection_run": _serialize_run(item)}

    status_code, result, _ = _idempotent(
        sessions, session, "create_collection_run", idempotency_key, payload, action
    )
    response.status_code = status_code
    return result


@router.get("/instagram/collection-runs/{run_id}")
def collection_run_status(
    run_id: UUID,
    session: Annotated[ManagementDeviceSession, Depends(require_management_session)],
    sessions: Annotated[sessionmaker[Session], Depends(get_sessions)],
) -> dict[str, Any]:
    with sessions() as db:
        item = db.get(InstagramCollectionRun, run_id)
        if item is None or item.account_id != session.account_id:
            raise ManagementError(404, "run_not_found", "Задача сбора не найдена.")
        return {"collection_run": _serialize_run(item)}


@router.post("/instagram/collection-runs/{run_id}/cancel")
def cancel_collection_run(
    run_id: UUID,
    response: Response,
    session: Annotated[ManagementDeviceSession, Depends(require_mutation)],
    sessions: Annotated[sessionmaker[Session], Depends(get_sessions)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    def action(db: Session) -> tuple[int, dict[str, Any]]:
        item = db.get(InstagramCollectionRun, run_id, with_for_update=True)
        if item is None or item.account_id != session.account_id:
            raise ManagementError(404, "run_not_found", "Задача сбора не найдена.")
        if item.status in {
            CollectionRunStatus.COMPLETED.value,
            CollectionRunStatus.FAILED.value,
            CollectionRunStatus.CANCELLED.value,
        }:
            return 200, {"collection_run": _serialize_run(item), "already_completed": True}
        item.cancel_requested_at = _now()
        if item.status == CollectionRunStatus.QUEUED.value:
            item.status = CollectionRunStatus.CANCELLED.value
            item.stop_reason_code = "CANCELLED_BY_USER"
            item.completed_at = _now()
        return 200, {"collection_run": _serialize_run(item), "already_completed": False}

    status_code, result, _ = _idempotent(
        sessions, session, "cancel_collection_run", idempotency_key, TargetRequest(target=1), action
    )
    response.status_code = status_code
    return result


@router.get("/instagram/normalization-status")
def normalization_status(
    _: Annotated[ManagementDeviceSession, Depends(require_management_session)],
    sessions: Annotated[sessionmaker[Session], Depends(get_sessions)],
) -> dict[str, int]:
    with sessions() as db:

        def count_job(status: str) -> int:
            return int(
                db.scalar(
                    select(func.count())
                    .select_from(InstagramNormalizationJob)
                    .where(InstagramNormalizationJob.status == status)
                )
                or 0
            )

        return {
            "pending": count_job("pending"),
            "running": count_job("running"),
            "completed": count_job("completed"),
            "failed": count_job("failed"),
            "cleanup_pending": int(
                db.scalar(
                    select(func.count())
                    .select_from(InstagramReel)
                    .where(InstagramReel.source_cleanup_pending.is_(True))
                )
                or 0
            ),
            "ready_count": int(
                db.scalar(
                    select(func.count())
                    .select_from(InstagramReel)
                    .where(InstagramReel.pipeline_status == "ready")
                )
                or 0
            ),
        }


@router.get("/instagram/collection-settings")
def collection_settings(
    session: Annotated[ManagementDeviceSession, Depends(require_management_session)],
    sessions: Annotated[sessionmaker[Session], Depends(get_sessions)],
) -> dict[str, Any]:
    with sessions() as db:
        item = db.get(InstagramCollectionSettings, session.account_id)
        return {
            "enabled": item.enabled if item else False,
            "target_reserve": item.target_reserve if item else 5,
            "scheduler_active": False,
        }


@router.put("/instagram/collection-settings")
def update_collection_settings(
    payload: SettingsRequest,
    response: Response,
    session: Annotated[ManagementDeviceSession, Depends(require_mutation)],
    sessions: Annotated[sessionmaker[Session], Depends(get_sessions)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    def action(db: Session) -> tuple[int, dict[str, Any]]:
        item = db.get(InstagramCollectionSettings, session.account_id, with_for_update=True)
        if item is None:
            item = InstagramCollectionSettings(
                account_id=session.account_id,
                enabled=payload.enabled,
                target_reserve=payload.target_reserve,
            )
            db.add(item)
        else:
            item.enabled = payload.enabled
            item.target_reserve = payload.target_reserve
        return 200, {
            "enabled": payload.enabled,
            "target_reserve": payload.target_reserve,
            "scheduler_active": False,
        }

    status_code, result, _ = _idempotent(
        sessions, session, "update_collection_settings", idempotency_key, payload, action
    )
    response.status_code = status_code
    return result


def install_management_error_handler(app) -> None:
    @app.exception_handler(ManagementError)
    async def management_error_handler(request: Request, error: ManagementError):
        from fastapi.responses import JSONResponse

        request_id = getattr(request.state, "request_id", str(uuid4()))
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {"code": error.code, "message": error.message, "request_id": request_id}
            },
            headers={"X-Request-ID": request_id, "Cache-Control": "no-store"},
        )

    @app.exception_handler(RequestValidationError)
    async def management_validation_handler(request: Request, error: RequestValidationError):
        if not request.url.path.startswith("/api/"):
            from fastapi.exception_handlers import request_validation_exception_handler

            return await request_validation_exception_handler(request, error)
        from fastapi.responses import JSONResponse

        request_id = getattr(request.state, "request_id", str(uuid4()))
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "invalid_request",
                    "message": "Некорректный запрос.",
                    "request_id": request_id,
                }
            },
            headers={"X-Request-ID": request_id, "Cache-Control": "no-store"},
        )

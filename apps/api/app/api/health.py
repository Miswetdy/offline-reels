import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request, status
from redis.asyncio import Redis

from app.core.settings import Settings
from app.db.database import check_postgres
from app.integrations.minio import check_minio

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


async def check_redis(settings: Settings) -> None:
    client = Redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=3)
    try:
        await client.ping()
    finally:
        await client.aclose()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/health/live")
async def live() -> dict[str, str]:
    """Confirm that FastAPI serves requests without checking dependencies."""
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request) -> dict[str, str]:
    """Confirm PostgreSQL and Redis only; MinIO is intentionally excluded."""
    settings = get_settings(request)
    try:
        await asyncio.to_thread(check_postgres, settings)
        await check_redis(settings)
    except Exception:
        logger.warning("Readiness check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unavailable"},
        ) from None

    return {"status": "ok"}


@router.get("/health/minio")
async def minio(request: Request) -> dict[str, str]:
    """Diagnostic endpoint. Its result never affects /health/ready."""
    settings = get_settings(request)
    try:
        await asyncio.to_thread(check_minio, settings)
    except Exception:
        logger.warning("MinIO diagnostic check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unavailable"},
        ) from None

    return {"status": "ok"}

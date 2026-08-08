"""Explicit Collector MinIO client factory; inert until called by an operator."""

from urllib.parse import urlparse

from minio import Minio
from urllib3 import PoolManager, Timeout

from app.core.settings import Settings


def create_collector_minio_client(settings: Settings) -> Minio:
    endpoint = urlparse(str(settings.minio_endpoint))
    return Minio(
        endpoint.netloc,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=endpoint.scheme == "https",
        http_client=PoolManager(
            timeout=Timeout(connect=10.0, read=30.0),
            retries=False,
        ),
    )

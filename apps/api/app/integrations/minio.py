from urllib.request import urlopen

from app.core.settings import Settings


def check_minio(settings: Settings) -> None:
    health_url = f"{str(settings.minio_endpoint).rstrip('/')}/minio/health/live"
    with urlopen(health_url, timeout=3) as response:  # noqa: S310 - endpoint comes from controlled config
        if response.status != 200:
            raise RuntimeError("MinIO live health check failed")

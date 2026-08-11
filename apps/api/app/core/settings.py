from functools import lru_cache

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False)

    app_env: str = "development"
    log_level: str = "INFO"
    frontend_origin: AnyHttpUrl = "http://localhost:3000"
    database_url: str = "postgresql+psycopg://offline_reels:change-me@localhost:5432/offline_reels"
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: AnyHttpUrl = "http://localhost:9000"
    minio_bucket: str = "offline-reels"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "change-me-local-minio-password"
    video_cursor_secret: str = Field(min_length=32)
    management_origin: AnyHttpUrl = "https://localhost:3000"
    login_gateway_origin: AnyHttpUrl = "https://login.example.invalid"
    management_session_ttl_minutes: int = Field(default=480, ge=5, le=1440)
    management_pairing_ttl_minutes: int = Field(default=10, ge=1, le=30)

    @field_validator("frontend_origin")
    @classmethod
    def frontend_origin_must_be_explicit(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if str(value).rstrip("/") == "*":
            raise ValueError("FRONTEND_ORIGIN must be an explicit origin")
        return value

    @field_validator("management_origin", "login_gateway_origin")
    @classmethod
    def management_origins_must_be_https(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.scheme != "https":
            raise ValueError("management origins must use HTTPS")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()

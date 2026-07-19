from functools import lru_cache

from pydantic import AnyHttpUrl, field_validator
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

    @field_validator("frontend_origin")
    @classmethod
    def frontend_origin_must_be_explicit(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if str(value).rstrip("/") == "*":
            raise ValueError("FRONTEND_ORIGIN must be an explicit origin")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()

"""Application configuration using pydantic-settings."""
from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_ENV: str = "development"
    APP_NAME: str = "JalDrishti API"
    APP_VERSION: str = "1.0.0"
    PORT: int = 8000

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:040812@localhost:5432/groundwater_db"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "groundwater_db"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "040812"

    # JWT
    JWT_SECRET: str = "change-this-secret"
    JWT_REFRESH_SECRET: str = "change-this-refresh-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # CORS (comma-separated)
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    # ML Service
    ML_SERVICE_URL: str = "http://localhost:8001"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Sentry
    SENTRY_DSN: str = ""

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # S3
    S3_BUCKET: str = ""
    S3_ENDPOINT_URL: str = ""
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

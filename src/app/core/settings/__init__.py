from functools import lru_cache

from pydantic import BaseModel, Field

from app.core.settings.app import AppSettings
from app.core.settings.base import (
    BaseContextSettings,
    _read_bool,
    _read_mute_loggers,
    _read_port,
    read_bool,
    read_mute_loggers,
    read_port,
)
from app.core.settings.idempotency import IdempotencySettings
from app.core.settings.internal_api import InternalAPISettings
from app.core.settings.jwt import JWTSettings
from app.core.settings.postgres import PostgresSettings
from app.core.settings.redis import RedisSettings


class Settings(BaseModel):
    """Корневой контейнер настроек сервиса."""

    app: AppSettings = Field(default_factory=AppSettings)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    idempotency: IdempotencySettings = Field(default_factory=IdempotencySettings)
    jwt: JWTSettings = Field(default_factory=JWTSettings)
    internal_api: InternalAPISettings = Field(default_factory=InternalAPISettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


__all__ = [
    "AppSettings",
    "BaseContextSettings",
    "IdempotencySettings",
    "InternalAPISettings",
    "JWTSettings",
    "PostgresSettings",
    "RedisSettings",
    "Settings",
    "_read_bool",
    "_read_mute_loggers",
    "_read_port",
    "get_settings",
    "read_bool",
    "read_mute_loggers",
    "read_port",
]

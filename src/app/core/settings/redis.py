from typing import Self

from pydantic import AliasChoices, Field, SecretStr, model_validator

from app.core.settings.base import BaseContextSettings


class RedisSettings(BaseContextSettings):
    url: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PROFILE_REDIS_URL",
            "PROFILE_VALKEY_URL",
            "TEST_IDEMPOTENCY_REDIS_URL",
            "REDIS_URL",
            "VALKEY_URL",
            "url",
        ),
    )
    host: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PROFILE_REDIS_HOST",
            "PROFILE_VALKEY_HOST",
            "REDIS_HOST",
            "VALKEY_HOST",
            "host",
        ),
    )
    port: int = Field(
        default=6379,
        ge=1,
        le=65535,
        validation_alias=AliasChoices(
            "PROFILE_REDIS_PORT",
            "PROFILE_VALKEY_PORT",
            "REDIS_PORT",
            "VALKEY_PORT",
            "port",
        ),
    )
    db: int = Field(
        default=0,
        ge=0,
        validation_alias=AliasChoices(
            "PROFILE_REDIS_DB",
            "PROFILE_VALKEY_DB",
            "REDIS_DB",
            "VALKEY_DB",
            "db",
        ),
    )
    key_namespace: str = Field(
        default="andruha-user-profile-service:idempotency:v2",
        validation_alias=AliasChoices(
            "PROFILE_REDIS_KEY_NAMESPACE",
            "KEY_NAMESPACE",
            "key_namespace",
        ),
    )
    max_connections: int = Field(default=10, gt=0)
    socket_timeout: float = Field(default=2.0, gt=0)
    socket_connect_timeout: float = Field(default=2.0, gt=0)
    health_check_interval: int = Field(default=30, ge=0)

    @model_validator(mode="after")
    def _validate_or_build_url(self) -> Self:
        if self.url is not None:
            return self
        if self.host:
            self.url = SecretStr(f"redis://{self.host}:{self.port}/{self.db}")
            return self
        raise ValueError(
            "Redis connection settings are required. "
            "Provide either 'REDIS_URL' or 'REDIS_HOST'."
        )

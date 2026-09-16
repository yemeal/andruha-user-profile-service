from typing import Self

from pydantic import AliasChoices, Field, SecretStr, model_validator
from sqlalchemy.engine import URL, make_url

from app.core.settings.base import BaseContextSettings


class PostgresSettings(BaseContextSettings):
    """PostgreSQL connection settings, configurable via URL or individual components."""

    database_url: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PROFILE_DATABASE_URL", "DATABASE_URL", "database_url"
        ),
    )
    host: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PROFILE_POSTGRES_HOST",
            "POSTGRES_HOST",
            "PROFILE_DATABASE_HOST",
            "DATABASE_HOST",
            "host",
        ),
    )
    port: int = Field(
        default=5432,
        ge=1,
        le=65535,
        validation_alias=AliasChoices(
            "PROFILE_POSTGRES_PORT",
            "POSTGRES_PORT",
            "PROFILE_DATABASE_PORT",
            "DATABASE_PORT",
            "port",
        ),
    )
    user: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PROFILE_POSTGRES_USER",
            "POSTGRES_USER",
            "PROFILE_DATABASE_USER",
            "DATABASE_USER",
            "user",
        ),
    )
    password: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PROFILE_POSTGRES_PASSWORD",
            "POSTGRES_PASSWORD",
            "PROFILE_DATABASE_PASSWORD",
            "DATABASE_PASSWORD",
            "password",
        ),
    )
    db: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "PROFILE_POSTGRES_DB",
            "POSTGRES_DB",
            "PROFILE_DATABASE_NAME",
            "DATABASE_NAME",
            "db",
            "name",
        ),
    )

    database_pool_size: int = Field(
        default=5,
        ge=1,
        le=100,
        validation_alias=AliasChoices(
            "PROFILE_DATABASE_POOL_SIZE",
            "DATABASE_POOL_SIZE",
            "database_pool_size",
            "pool_size",
        ),
    )
    database_max_overflow: int = Field(
        default=5,
        ge=0,
        le=100,
        validation_alias=AliasChoices(
            "PROFILE_DATABASE_MAX_OVERFLOW",
            "DATABASE_MAX_OVERFLOW",
            "database_max_overflow",
            "max_overflow",
        ),
    )
    database_pool_timeout: float = Field(
        default=5.0,
        gt=0,
        validation_alias=AliasChoices(
            "PROFILE_DATABASE_POOL_TIMEOUT",
            "DATABASE_POOL_TIMEOUT",
            "database_pool_timeout",
            "pool_timeout",
        ),
    )
    database_command_timeout: float = Field(
        default=10.0,
        gt=0,
        validation_alias=AliasChoices(
            "PROFILE_DATABASE_COMMAND_TIMEOUT",
            "DATABASE_COMMAND_TIMEOUT",
            "database_command_timeout",
            "command_timeout",
        ),
    )

    @model_validator(mode="after")
    def _validate_or_build_url(self) -> Self:
        if self.database_url is not None:
            raw_url = self.database_url.get_secret_value()
            try:
                parsed = make_url(raw_url)
            except Exception:
                raise ValueError("Invalid PostgreSQL URL") from None
            if parsed.drivername != "postgresql+asyncpg" or not parsed.database:
                raise ValueError("Use postgresql+asyncpg with an explicit database")
            return self

        if self.host and self.user and self.password is not None and self.db:
            password_str = self.password.get_secret_value()
            url_obj = URL.create(
                drivername="postgresql+asyncpg",
                username=self.user,
                password=password_str,
                host=self.host,
                port=self.port,
                database=self.db,
            )
            self.database_url = SecretStr(url_obj.render_as_string(hide_password=False))
            return self

        raise ValueError(
            "PostgreSQL connection settings are required. "
            "Provide either 'DATABASE_URL' or ('POSTGRES_HOST', 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB')."
        )

    @property
    def url(self) -> SecretStr:
        assert self.database_url is not None
        return self.database_url

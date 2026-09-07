from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class DatabaseSettings(BaseSettings):
    """Loaded explicitly by composition roots, never at module import."""

    model_config = SettingsConfigDict(env_prefix="PROFILE_", extra="ignore")
    database_url: SecretStr
    database_pool_size: int = Field(default=5, ge=1, le=100)
    database_max_overflow: int = Field(default=5, ge=0, le=100)
    database_pool_timeout: float = Field(default=5, gt=0)
    database_command_timeout: float = Field(default=10, gt=0)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        try:
            url = make_url(value.get_secret_value())
        except Exception:
            raise ValueError("Invalid PostgreSQL URL") from None
        if url.drivername != "postgresql+asyncpg" or not url.database:
            raise ValueError("Use postgresql+asyncpg with an explicit database")
        return value

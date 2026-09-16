from typing import Annotated, Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import NoDecode

from app.core.settings.base import BaseContextSettings


class AppSettings(BaseContextSettings):
    service_name: str = Field(
        default="andruha-user-profile-service",
        validation_alias=AliasChoices("SERVICE_NAME", "service_name"),
    )
    version: str = Field(
        default="0.1.0",
        validation_alias=AliasChoices("APP_VERSION", "VERSION", "version"),
    )
    environment: Literal["development", "test", "production"] = Field(
        default="development",
        validation_alias=AliasChoices("APP_ENVIRONMENT", "ENVIRONMENT", "environment"),
    )
    host: str = Field(
        default="0.0.0.0",
        validation_alias=AliasChoices("HOST", "host"),
    )
    port: int = Field(
        default=8002,
        ge=1,
        le=65535,
        validation_alias=AliasChoices("PORT", "port"),
    )
    dev_logs: bool = Field(
        default=True,
        validation_alias=AliasChoices("DEV_LOGS", "dev_logs"),
    )
    log_level: str = Field(
        default="INFO",
        validation_alias=AliasChoices("LOG_LEVEL", "log_level"),
    )
    mute_loggers: Annotated[tuple[str, ...], NoDecode] = Field(
        default=("uvicorn.access",),
        validation_alias=AliasChoices("MUTE_LOGGERS", "mute_loggers"),
    )

    @field_validator("service_name")
    @classmethod
    def non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("service name must not be blank")
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("mute_loggers", mode="before")
    @classmethod
    def normalize_mute_loggers(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return value

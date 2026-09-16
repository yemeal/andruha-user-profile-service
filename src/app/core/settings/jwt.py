"""Access-token verification configuration."""

from pathlib import Path
from typing import Annotated

from pydantic import Field, StringConstraints
from pydantic_settings import SettingsConfigDict

from app.core.settings.base import BaseContextSettings

TrustedKeyId = Annotated[str, StringConstraints(min_length=1, pattern=r"^\S+$")]
NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class JWTSettings(BaseContextSettings):
    model_config = SettingsConfigDict(env_prefix="JWT_", frozen=True)

    public_keys: dict[TrustedKeyId, Path] = Field(default_factory=dict)
    issuer: NonBlank = "andruha-identity-service"
    audience: NonBlank = "andruha-user-profile-service"
    clock_skew_seconds: int = Field(default=30, ge=0)

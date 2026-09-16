"""Credentials for trusted service-to-service provisioning."""

from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict

from app.core.settings.base import BaseContextSettings


class InternalAPISettings(BaseContextSettings):
    model_config = SettingsConfigDict(env_prefix="INTERNAL_API_", frozen=True)

    token: SecretStr | None = None

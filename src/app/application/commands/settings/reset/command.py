import uuid

from pydantic import Field

from app.application.commands.base import BaseCommand


class ResetSettingsCommand(BaseCommand):
    """
    Команда сброса настроек пользователя к дефолтным значениям.
    """

    user_id: uuid.UUID = Field(
        description="Идентификатор пользователя (UUIDv7)",
    )
    expected_version: int = Field(
        ge=1,
        description="Ожидаемый номер версии настроек для оптимистической блокировки (OCC)",
    )

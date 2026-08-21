from datetime import datetime
from uuid import UUID

from app.application.ports.persistence.repositories.base import (
    AsyncRepositoryProtocol,
)
from app.domain.aggregates.settings import UserSettings


class SettingsRepositoryProtocol(AsyncRepositoryProtocol[UserSettings, UUID]):
    """
    Порт репозитория для работы с агрегатами настроек пользователей (UserSettings).
    """

    async def create_default_if_absent(
        self, user_id: UUID, now: datetime
    ) -> UserSettings:
        """
        Атомарная операция создания дефолтных настроек при отсутствии.

        Если настройки уже существуют - возвращает существующие.
        """
        ...

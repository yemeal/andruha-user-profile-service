from typing import Protocol
from uuid import UUID

from app.domain.aggregates.settings import UserSettings


class SettingsReaderProtocol(Protocol):
    """
    Порт чтения данных настроек пользователя (Read Side / Projections).
    """

    async def get_by_id(self, user_id: UUID) -> UserSettings | None:
        """
        Получить настройки по идентификатору пользователя.
        """
        ...

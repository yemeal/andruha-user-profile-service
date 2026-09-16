from typing import Protocol
from uuid import UUID

from app.application.ports.persistence.readers.base import AsyncReaderProtocol
from app.domain.aggregates.profiles import UserProfile
from app.domain.value_objects.username import Username


class ProfileReaderProtocol(AsyncReaderProtocol[UserProfile, UUID], Protocol):
    """
    Порт чтения данных профилей (Read Side / Projections).
    Используется для query handlers, поиска и пакетных выборок без изменения состояния.
    """

    async def get_by_username(self, username: Username | str) -> UserProfile | None:
        """
        Получить профиль пользователя по уникальному никнейму.
        """
        ...

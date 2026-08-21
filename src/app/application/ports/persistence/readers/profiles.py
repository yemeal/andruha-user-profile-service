from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.domain.aggregates.profiles import UserProfile
from app.domain.value_objects.username import Username


class ProfileReaderProtocol(Protocol):
    """
    Порт чтения данных профилей (Read Side / Projections).
    Используется для query handlers, поиска и пакетных выборок без изменения состояния.
    """

    async def get_by_id(self, user_id: UUID) -> UserProfile | None:
        """
        Получить профиль по идентификатору пользователя.
        """
        ...

    async def get_by_username(self, username: Username | str) -> UserProfile | None:
        """
        Получить профиль пользователя по уникальному никнейму.
        """
        ...

    async def get_batch(self, user_ids: Sequence[UUID]) -> list[UserProfile]:
        """
        Пакетное получение профилей пользователей по списку идентификаторов.
        """
        ...

    async def exists(self, user_id: UUID) -> bool:
        """
        Проверить факт существования профиля пользователя.
        """
        ...

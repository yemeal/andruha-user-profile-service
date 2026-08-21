from datetime import datetime
from uuid import UUID

from app.application.ports.persistence.repositories.base import (
    AsyncRepositoryProtocol,
)
from app.domain.aggregates.profiles import UserProfile


class ProfileRepositoryProtocol(AsyncRepositoryProtocol[UserProfile, UUID]):
    """
    Порт репозитория для работы с агрегатами профилей пользователей (UserProfile).
    Фокусируется на операциях изменения и загрузки агрегата.
    """

    async def create_default_if_absent(
        self, user_id: UUID, now: datetime
    ) -> UserProfile:
        """
        Атомарная операция создания дефолтного профиля при отсутствии.

        Если профиль уже существует — возвращает существующий.
        """
        ...

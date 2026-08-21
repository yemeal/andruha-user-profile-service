import uuid
from datetime import datetime

from pydantic import Field

from app.application.queries.base import BaseQueryResult
from app.domain.value_objects.status import UserProfileStatus


class ProfileDTO(BaseQueryResult):
    """
    Полное представление профиля пользователя (для владельца).
    """

    user_id: uuid.UUID = Field(
        description="Уникальный идентификатор пользователя (UUIDv7)",
    )
    username: str | None = Field(
        default=None,
        description="Уникальный никнейм пользователя",
    )
    display_name: str = Field(
        description="Отображаемое имя профиля",
    )
    bio: str | None = Field(
        default=None,
        description="Краткое описание/биография профиля",
    )
    avatar_key: str | None = Field(
        default=None,
        description="Ключ аватара в объектном хранилище",
    )
    status: UserProfileStatus = Field(
        description="Текущий статус жизненного цикла профиля (ACTIVE, DISABLED, BLOCKED)",
    )
    is_verified: bool = Field(
        description="Флаг верификации профиля",
    )
    version: int = Field(
        description="Текущий номер версии профиля для оптимистической блокировки (OCC)",
    )
    created_at: datetime = Field(
        description="Дата создания профиля (UTC)",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="Дата последнего обновления профиля (UTC)",
    )


MyProfileResult = ProfileDTO

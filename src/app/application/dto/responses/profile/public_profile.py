import uuid

from pydantic import Field

from app.application.dto.base import BaseResponse


class PublicProfileDTO(BaseResponse):
    """
    Публичное DTO представление профиля для третьих лиц.
    Поля bio и avatar_key маскируются в None, если настройки приватности целевого
    пользователя ограничивают их видимость.
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
        description="Описание профиля (скрыто, если ограничено приватностью)",
    )
    avatar_key: str | None = Field(
        default=None,
        description="Ключ аватара (скрыт, если ограничен приватностью)",
    )
    is_verified: bool = Field(
        description="Флаг верификации профиля",
    )

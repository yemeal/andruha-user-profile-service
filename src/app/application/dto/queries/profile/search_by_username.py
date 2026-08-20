import uuid

from pydantic import Field

from app.application.dto.base import BaseQuery


class SearchByUsernameQuery(BaseQuery):
    """
    Запрос на поиск публичного профиля по уникальному никнейму (username).
    """

    username: str = Field(
        min_length=3,
        max_length=32,
        description="Искомый публичный никнейм пользователя",
    )
    viewer_id: uuid.UUID | None = Field(
        default=None,
        description="Идентификатор просматривающего пользователя (для проверки приватности)",
    )

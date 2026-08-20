import uuid

from pydantic import Field

from app.application.dto.base import BaseQuery


class GetPublicProfileQuery(BaseQuery):
    """
    Запрос на получение публичной информации профиля целевого пользователя.
    """

    user_id: uuid.UUID = Field(
        description="Идентификатор запрашиваемого пользователя (UUIDv7)",
    )
    viewer_id: uuid.UUID | None = Field(
        default=None,
        description="Идентификатор просматривающего пользователя (для проверки приватности)",
    )

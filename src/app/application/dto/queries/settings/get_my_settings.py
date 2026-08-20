import uuid

from pydantic import Field

from app.application.dto.base import BaseQuery


class GetMySettingsQuery(BaseQuery):
    """
    Запрос на получение настроек интерфейса текущего пользователя.
    """

    user_id: uuid.UUID = Field(
        description="Идентификатор текущего пользователя (UUIDv7)",
    )

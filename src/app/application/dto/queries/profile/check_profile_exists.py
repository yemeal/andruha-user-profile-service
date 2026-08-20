import uuid

from pydantic import Field

from app.application.dto.base import BaseQuery


class CheckProfileExistsQuery(BaseQuery):
    """
    Запрос на проверку факта существования профиля пользователя.
    """

    user_id: uuid.UUID = Field(
        description="Идентификатор проверяемого пользователя (UUIDv7)",
    )

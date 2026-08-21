import uuid

from pydantic import Field

from app.application.queries.base import BaseQuery


class GetMyProfileQuery(BaseQuery):
    """
    Запрос на получение собственного профиля текущего авторизованного пользователя.
    """

    user_id: uuid.UUID = Field(
        description="Идентификатор текущего пользователя (UUIDv7)",
    )

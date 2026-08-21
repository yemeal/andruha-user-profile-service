import uuid

from pydantic import Field, field_validator

from app.application.queries.base import BaseQuery


class GetBatchProfilesQuery(BaseQuery):
    """
    Запрос на пакетное получение публичных профилей пользователей.
    Лимит: от 1 до 100 уникальных идентификаторов.
    """

    user_ids: list[uuid.UUID] = Field(
        min_length=1,
        max_length=100,
        description="Список идентификаторов запрашиваемых пользователей (1..100)",
    )
    viewer_id: uuid.UUID | None = Field(
        default=None,
        description="Идентификатор просматривающего пользователя",
    )

    @field_validator("user_ids")
    @classmethod
    def deduplicate_user_ids(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        """
        Дедуплицирует список идентификаторов с сохранением исходного порядка.

        Используется list(dict.fromkeys(v)), так как в Python 3.7+ хэш-таблица словарей
        гарантирует сохранение порядка добавления (insertion order) и выполняется
        полностью на Си-уровне внутри CPython, обеспечивая O(N) скорость без лишних аллокаций.
        """
        return list(dict.fromkeys(v))

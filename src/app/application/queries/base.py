from typing import Any

from pydantic import BaseModel, ConfigDict

from app.application.dto.base import BaseDTO


class BaseQuery(BaseModel):
    """
    Базовый запрос на чтение данных (Query).
    Не производит побочных эффектов, неизменяем и запрещает лишние параметры.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
        from_attributes=True,
    )

    def to_params(self) -> dict[str, Any]:
        """Возвращает параметры запроса в виде словаря."""
        return self.model_dump()


# Алиасы для обратной совместимости
BaseQueryResult = BaseDTO
BaseResponse = BaseDTO

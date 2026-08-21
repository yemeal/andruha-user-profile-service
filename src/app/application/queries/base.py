from typing import Any, Self

from pydantic import BaseModel, ConfigDict


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


class BaseQueryResult(BaseModel):
    """
    Базовая модель результата запроса на чтение (Read Model / Result / Projection).
    Поддерживает неизменяемость и бесшовную гидратацию из доменных сущностей.
    """

    model_config = ConfigDict(
        frozen=True,
        from_attributes=True,
        populate_by_name=True,
    )

    @classmethod
    def from_domain(cls, entity: Any) -> Self:
        """
        Построение DTO/Result ответа из доменной сущности или агрегата.
        """
        return cls.model_validate(entity)


# Для обратной совместимости
BaseResponse = BaseQueryResult

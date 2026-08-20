from typing import Any, Self

from pydantic import BaseModel, ConfigDict


class BaseDTO(BaseModel):
    """Базовый класс для всех DTO прикладного слоя."""

    model_config = ConfigDict(
        frozen=True,
        populate_by_name=True,
        from_attributes=True,
    )


class BaseCommand(BaseDTO):
    """
    Базовая команда на изменение состояния системы (Command).
    Всегда неизменяема (frozen=True) и строго запрещает лишние поля (extra='forbid').
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
        from_attributes=True,
    )

    def non_none_fields(self, exclude: set[str] | None = None) -> dict[str, Any]:
        """
        Возвращает словарь только установленных полей (значения которых не None).
        Удобно для частичных обновлений в PATCH сценариях.
        """
        exclude_keys = exclude or set()
        return {
            k: v
            for k, v in self.model_dump().items()
            if v is not None and k not in exclude_keys
        }

    def to_dict(self) -> dict[str, Any]:
        """Сериализация команды в словарь."""
        return self.model_dump()


class BaseQuery(BaseDTO):
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


class BaseResponse(BaseDTO):
    """
    Базовая модель ответа (Read DTO / Projection).
    Поддерживает бесшовную гидратацию из доменных агрегатов и ORM-моделей.
    """

    model_config = ConfigDict(
        frozen=True,
        from_attributes=True,
        populate_by_name=True,
    )

    @classmethod
    def from_domain(cls, entity: Any) -> Self:
        """
        Построение DTO ответа из доменной сущности или агрегата.
        """
        return cls.model_validate(entity)

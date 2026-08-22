from typing import Any, Self

from pydantic import BaseModel, ConfigDict


class BaseDTO(BaseModel):
    """
    Базовая модель передачи данных (Data Transfer Object / Read Model).
    Неизменяема (frozen=True), поддерживает ORM/Domain гидратацию.
    """

    model_config = ConfigDict(
        frozen=True,
        from_attributes=True,
        populate_by_name=True,
    )

    @classmethod
    def from_domain(cls, entity: Any) -> Self:
        """Построение DTO ответа из доменной сущности или агрегата."""
        return cls.model_validate(entity)


# Для обратной совместимости
BaseResponse = BaseDTO

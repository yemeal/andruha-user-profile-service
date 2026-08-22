from typing import Any

from pydantic import BaseModel, ConfigDict


class BaseCommand[ResultT](BaseModel):
    """
    Базовая команда на изменение состояния системы (Command).
    Всегда неизменяема (frozen=True) и строго запрещает лишние поля (extra='forbid').
    Параметризована типом ожидаемого результата ResultT (обязательно указывать).
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

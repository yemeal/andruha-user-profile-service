import uuid
from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.clock import utc_now
from app.domain.exceptions.base import InvalidTimestampError


class DomainModel(BaseModel):
    """
    Базовая модель домена.

    Особенности конфигурации:
    - from_attributes=True: поддержка построения из ORM-моделей и произвольных объектов;
    - validate_assignment=True: автоматическая валидация полей при присваивании;
    - populate_by_name=True: возможность создания как по имени поля, так и по alias.
    """

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        populate_by_name=True,
    )


class Entity(DomainModel):
    """
    Базовая сущность домена с уникальным идентификатором и временем создания.
    """

    id: uuid.UUID = Field(
        frozen=True,
        default_factory=uuid.uuid7,
        description="Уникальный идентификатор сущности (UUIDv7)",
    )
    created_at: datetime = Field(
        frozen=True,
        default_factory=utc_now,
        description="Дата и время создания сущности (UTC)",
    )


class MutableEntity(Entity):
    """
    Изменяемая сущность домена с опциональным временем последнего обновления.
    """

    updated_at: datetime | None = Field(
        frozen=True,
        default=None,
        description="Дата и время последнего обновления сущности (UTC)",
    )

    @model_validator(mode="after")
    def _validate_timestamps(self) -> Self:
        if self.updated_at is not None and self.updated_at <= self.created_at:
            raise InvalidTimestampError()
        return self

    def _replace_state(self, candidate: Self) -> None:
        """Применяет уже проверенное состояние без последовательных присваиваний.

        Все потенциальные ошибки валидации возникают при создании candidate,
        пока исходный объект ещё не изменён. Вложенные значения агрегатов неизменяемы.
        """
        object.__setattr__(self, "__dict__", candidate.__dict__.copy())
        object.__setattr__(
            self, "__pydantic_fields_set__", candidate.model_fields_set.copy()
        )

    def mark_updated(self, now: datetime) -> None:
        candidate = self.__class__.model_validate(
            {
                **self.model_dump(),
                "updated_at": now,
            }
        )
        self._replace_state(candidate)


class VersionedMutableEntity(MutableEntity):
    """Версия и время изменяются вместе после проверки полного нового состояния.

    Гидратация из БД использует model_validate. При доменном изменении
    _apply_changes проверяет значения и время, затем заменяет состояние целиком.
    Проверка версии при конкурентной записи остаётся обязанностью репозитория.
    """

    version: int = Field(
        default=1,
        ge=1,
        frozen=True,
        description="Номер версии сущности (изменяется вместе с updated_at)",
    )

    def _apply_changes(self, *, now: datetime, **changes: Any) -> bool:
        # Сначала валидируем и нормализуем бизнес-поля на отдельном объекте.
        candidate = self.__class__.model_validate(
            {
                **self.model_dump(),
                **changes,
            }
        )

        if candidate == self:
            return False

        # Даже ошибка времени не должна оставлять частичное изменение.
        candidate.mark_updated(now)
        self._replace_state(candidate)
        return True

    def mark_updated(self, now: datetime) -> None:
        candidate = self.__class__.model_validate(
            {
                **self.model_dump(),
                "updated_at": now,
                "version": self.version + 1,
            }
        )
        self._replace_state(candidate)

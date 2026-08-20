import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.clock import utc_now
from app.domain.exceptions.base import InvalidTimestampError, InvalidVersionError


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
        default_factory=uuid.uuid7,
        description="Уникальный идентификатор сущности (UUIDv7)",
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        description="Дата и время создания сущности (UTC)",
    )


class MutableEntity(Entity):
    """
    Изменяемая сущность домена с опциональным временем последнего обновления.
    """

    updated_at: datetime | None = Field(
        default=None,
        description="Дата и время последнего обновления сущности (UTC)",
    )

    @model_validator(mode="after")
    def _validate_timestamps(self) -> Self:
        if self.updated_at is not None and self.updated_at <= self.created_at:
            raise InvalidTimestampError()
        return self

    def mark_updated(self, now: datetime) -> None:
        """
        Фиксирует факт изменения сущности, обновляя метку времени последнего обновления.
        """
        self.updated_at = now


class VersionedMutableEntity(MutableEntity):
    """
    Изменяемая сущность с поддержкой версионирования для оптимистической блокировки (OCC).
    """

    version: int = Field(
        default=1,
        description="Номер версии сущности для оптимистической блокировки (начиная с 1)",
    )

    @model_validator(mode="after")
    def _validate_version(self) -> Self:
        if self.version < 1:
            raise InvalidVersionError()
        return self

    def increment_version(self) -> None:
        """
        Инкрементирует номер версии сущности при успешной мутации состояния.
        """
        self.version += 1

    def mark_updated(self, now: datetime) -> None:
        """
        Фиксирует факт изменения сущности, обновляя метку времени и инкрементируя версию.
        """
        super().mark_updated(now)
        self.increment_version()

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class IdempotencyKey(BaseModel):
    """Неизменяемый составной идентификатор идемпотентной операции в рамках субъекта."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject_id: str = Field(
        min_length=1,
        max_length=255,
        description="Идентификатор субъекта/пользователя, в рамках которого изолирован ключ",
    )
    operation: str = Field(
        min_length=1,
        max_length=100,
        description="Наименование выполняемой операции или команды",
    )
    key_digest: bytes = Field(
        min_length=32,
        max_length=32,
        description="32-байтный SHA-256 хэш клиентского ключа идемпотентности",
    )


class ClaimStatus(StrEnum):
    """Статус попытки захвата распределенной блокировки (lease claim) в кэше."""

    ACQUIRED = "ACQUIRED"
    REPLAY = "REPLAY"
    CONFLICT = "CONFLICT"
    IN_PROGRESS = "IN_PROGRESS"


class StoredResult(BaseModel):
    """Сериализованный результат выполнения операции, готовый к сохранению в кэше или БД."""

    model_config = ConfigDict(extra="forbid")

    result_type: str = Field(
        min_length=1,
        max_length=100,
        description="Тип сохраненного результата (имя DTO или примитивного типа)",
    )
    result_payload: dict[str, Any] | None = Field(
        default=None,
        description="Словарь данных результата выполнения",
    )
    result_version: int = Field(
        default=1,
        gt=0,
        description="Версия схемы сериализации результата",
    )
    resource_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Тип измененного доменного ресурса",
    )
    resource_id: str | None = Field(
        default=None,
        description="Идентификатор измененного доменного ресурса",
    )
    resource_version: int | None = Field(
        default=None,
        gt=0,
        description="Версия агрегата/ресурса после применения команды",
    )

    @field_validator("resource_id", mode="before")
    @classmethod
    def normalize_resource_id(cls, value: object) -> object:
        return str(value) if isinstance(value, UUID) else value

    @model_validator(mode="after")
    def validate_replayability(self) -> StoredResult:
        has_type = self.resource_type is not None
        has_id = self.resource_id is not None
        if has_type != has_id:
            raise ValueError(
                "Параметры resource_type и resource_id должны указываться совместно"
            )
        if self.result_payload is None and not has_id:
            raise ValueError(
                "Сохраненный результат требует наличия полезной нагрузки или ссылки на ресурс"
            )
        if self.resource_version is not None and not has_id:
            raise ValueError(
                "Параметр resource_version требует наличия ссылки на ресурс"
            )
        return self


class CompletedIdempotencyResult(StoredResult):
    """Завершенный результат выполнения, связанный со слепком (fingerprint) исходного запроса."""

    request_fingerprint: bytes = Field(
        min_length=32,
        max_length=32,
        description="32-байтный SHA-256 слепок тела команды/запроса",
    )


class ClaimResult(BaseModel):
    """Результат попытки захвата распределенной блокировки в горячем хранилище."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ClaimStatus
    completed: CompletedIdempotencyResult | None = None

    @model_validator(mode="after")
    def validate_decision(self) -> ClaimResult:
        if self.status is ClaimStatus.REPLAY and self.completed is None:
            raise ValueError("Статус REPLAY требует наличия завершенного результата")
        if self.status is not ClaimStatus.REPLAY and self.completed is not None:
            raise ValueError(
                "Только статус REPLAY может содержать завершенный результат"
            )
        return self


class ExecutionStatus(StrEnum):
    """Итоговый статус выполнения идемпотентного пайплайна."""

    EXECUTED = "EXECUTED"
    REPLAY = "REPLAY"
    CONFLICT = "CONFLICT"
    IN_PROGRESS = "IN_PROGRESS"


class IdempotencyResult(BaseModel):
    """Итоговое решение координатора идемпотентности."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ExecutionStatus
    completed: CompletedIdempotencyResult | None = None

    @model_validator(mode="after")
    def validate_decision(self) -> IdempotencyResult:
        carries_result = self.status in {
            ExecutionStatus.EXECUTED,
            ExecutionStatus.REPLAY,
        }
        if carries_result != (self.completed is not None):
            raise ValueError(
                "Статус выполнения не согласуется с наличием завершенного результата"
            )
        return self

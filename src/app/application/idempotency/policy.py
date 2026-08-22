from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class IdempotencyMode(StrEnum):
    """
    Режим выполнения идемпотентной операции.

    - HOT_ONLY: быстрый путь через кэш с семантикой fail-closed при недоступности кэша.
    - HOT_DURABLE: быстрый путь через кэш с деградацией до транзакционного выполнения в БД.
    """

    HOT_ONLY = "HOT_ONLY"
    HOT_DURABLE = "HOT_DURABLE"


class IdempotencyPolicy(BaseModel):
    """Политика, определяющая режим и параметры гарантий идемпотентности команды."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: IdempotencyMode = Field(
        default=IdempotencyMode.HOT_DURABLE,
        description="Режим выполнения идемпотентности (HOT_ONLY или HOT_DURABLE)",
    )
    lease_seconds: int = Field(
        default=30,
        gt=0,
        description="Время удержания распределенной блокировки (lease lock) в секундах",
    )

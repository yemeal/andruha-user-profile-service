from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.application.idempotency.models import (
        CompletedIdempotencyResult,
        IdempotencyKey,
    )


class DurableIdempotencyStore(Protocol):
    """Порт постоянного хранения результатов выполненных идемпотентных операций в БД."""

    async def get_completed(
        self, identity: IdempotencyKey
    ) -> CompletedIdempotencyResult | None:
        """Получение сохраненного результата по ключу идемпотентности."""
        ...

    async def try_add_completed(
        self, identity: IdempotencyKey, completed: CompletedIdempotencyResult
    ) -> bool:
        """Попытка добавления записи о завершении операции (с защитой от дублей)."""
        ...

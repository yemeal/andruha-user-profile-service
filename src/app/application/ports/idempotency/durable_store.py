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
        """Возвращает только действующий результат с исходным expires_at."""
        ...

    async def try_add_completed(
        self, identity: IdempotencyKey, completed: CompletedIdempotencyResult
    ) -> bool:
        """Условно сохраняет результат в общей бизнес-транзакции без commit.

        Действующий winner не перезаписывается: возвращается False.
        Истёкшую запись можно заменить атомарно; expires_at не продлевается.
        """
        ...

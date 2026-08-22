from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.application.idempotency.models import (
    CompletedIdempotencyResult,
    ExecutionStatus,
    IdempotencyKey,
    IdempotencyResult,
    StoredResult,
)
from app.application.ports.idempotency.durable_store import DurableIdempotencyStore
from app.application.ports.persistence.unit_of_work import AsyncUOWProtocol

IdempotentOperation = Callable[[], Awaitable[StoredResult]]


class _ConcurrentWinnerCommitted(Exception):
    """Служебное исключение: параллельный запрос уже закоммитил запись в БД."""


class TransactionalIdempotencyExecution:
    """
    Атомарная привязка записи об идемпотентности к бизнес-транзакции в рамках единого Unit of Work.

    Обработчик обязан выполнять только транзакционные операции записи через общий UoW.
    Внешние сайд-эффекты и сетевой ввод/вывод внутри транзакции запрещены.
    """

    def __init__(
        self,
        durable_store: DurableIdempotencyStore,
        uow: AsyncUOWProtocol,
    ) -> None:
        self._durable_store = durable_store
        self._uow = uow

    async def execute_once(
        self,
        identity: IdempotencyKey,
        request_fingerprint: bytes,
        operation: IdempotentOperation,
    ) -> IdempotencyResult:
        """Однократное выполнение бизнес-операции в транзакции с защитой от гонок."""
        _validate_fingerprint(request_fingerprint)
        existing = await self.find_existing(identity, request_fingerprint)
        if existing is not None:
            return existing

        try:
            async with self._uow:
                stored = await operation()
                completed = CompletedIdempotencyResult(
                    request_fingerprint=request_fingerprint,
                    **stored.model_dump(),
                )
                if not await self._durable_store.try_add_completed(identity, completed):
                    # Откатываем транзакцию, если параллельный процесс уже закоммитил этот ключ.
                    raise _ConcurrentWinnerCommitted
        except _ConcurrentWinnerCommitted as race_error:
            winner = await self.find_existing(identity, request_fingerprint)
            if winner is None:
                raise RuntimeError(
                    "Конфликт уникальности идемпотентности без зафиксированного победителя"
                ) from race_error
            return winner
        except Exception as operation_error:
            # Параллельные запросы могут одновременно пройти первичную проверку.
            # После отката перечитываем результат победителя вместо выброса устаревшей ошибки.
            try:
                winner = await self.find_existing(identity, request_fingerprint)
            except Exception as lookup_error:
                raise operation_error from lookup_error
            if winner is not None:
                return winner
            raise

        return IdempotencyResult(
            status=ExecutionStatus.EXECUTED,
            completed=completed,
        )

    async def find_existing(
        self,
        identity: IdempotencyKey,
        request_fingerprint: bytes,
    ) -> IdempotencyResult | None:
        """Поиск и классификация существующей записи в постоянном хранилище."""
        _validate_fingerprint(request_fingerprint)
        async with self._uow:
            existing = await self._durable_store.get_completed(identity)
        if existing is None:
            return None
        return _classify(existing, request_fingerprint)


def _validate_fingerprint(request_fingerprint: bytes) -> None:
    if len(request_fingerprint) != 32:
        raise ValueError(
            "Параметр request_fingerprint должен быть 32-байтным SHA-256 дайджестом"
        )


def _classify(
    completed: CompletedIdempotencyResult,
    request_fingerprint: bytes,
) -> IdempotencyResult:
    if completed.request_fingerprint != request_fingerprint:
        return IdempotencyResult(status=ExecutionStatus.CONFLICT)
    return IdempotencyResult(
        status=ExecutionStatus.REPLAY,
        completed=completed,
    )

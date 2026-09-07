from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta

from app.application.exceptions.idempotency import IdempotencyUnavailableError
from app.application.exceptions.persistence import (
    PersistenceUnavailableError,
    TransactionConflictError,
)
from app.application.idempotency.models import (
    CompletedIdempotencyResult,
    ExecutionStatus,
    IdempotencyKey,
    IdempotencyResult,
)
from app.application.ports.idempotency.durable_execution import IdempotentOperation
from app.application.ports.idempotency.durable_store import DurableIdempotencyStore
from app.application.ports.persistence.unit_of_work import AsyncUOWProtocol
from app.domain.clock import utc_now


class _ConcurrentWinnerCommitted(Exception):
    """Internal signal used to roll back the losing business transaction."""


class TransactionalIdempotencyExecution:
    """Commit the local business effect and replay record in one transaction.

    Scope: one dispatch at a time. The handler repositories, durable store and UoW
    must share the same session. UoW must support sequential transaction contexts
    and roll back on any BaseException. Handlers must not commit independently or
    perform external effects; use a transactional outbox for those.

    This adapter requires rollback-capable local transactions. It is not a
    generic Cassandra transaction implementation.
    """

    def __init__(
        self,
        durable_store: DurableIdempotencyStore,
        uow: AsyncUOWProtocol,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._clock = clock
        self._durable_store = durable_store
        self._uow = uow
        self._active = False

    @contextmanager
    def _exclusive_use(self) -> Iterator[None]:
        # The check and assignment contain no await: competing tasks cannot
        # accidentally enter the same session while this execution is active.
        if self._active:
            raise RuntimeError(
                "TransactionalIdempotencyExecution requires a separate scope per concurrent dispatch"
            )
        self._active = True
        try:
            yield
        finally:
            self._active = False

    async def execute_once(
        self,
        identity: IdempotencyKey,
        request_fingerprint: bytes,
        operation: IdempotentOperation,
        *,
        retention_seconds: int,
    ) -> IdempotencyResult:
        with self._exclusive_use():
            if retention_seconds <= 0:
                raise ValueError("retention_seconds must be positive")
            try:
                return await self._execute_once(
                    identity, request_fingerprint, operation, retention_seconds
                )
            except PersistenceUnavailableError as error:
                raise IdempotencyUnavailableError(
                    "Durable execution unavailable; commit outcome may be unknown"
                ) from error

    async def _execute_once(
        self,
        identity: IdempotencyKey,
        request_fingerprint: bytes,
        operation: IdempotentOperation,
        retention_seconds: int,
    ) -> IdempotencyResult:
        _validate_fingerprint(request_fingerprint)
        existing = await self._find_existing(identity, request_fingerprint)
        if existing is not None:
            return existing

        try:
            async with self._uow:
                stored = await operation()
                completed = CompletedIdempotencyResult(
                    request_fingerprint=request_fingerprint,
                    expires_at=self._clock() + timedelta(seconds=retention_seconds),
                    **stored.model_dump(),
                )
                if not await self._durable_store.try_add_completed(identity, completed):
                    raise _ConcurrentWinnerCommitted
        except (_ConcurrentWinnerCommitted, TransactionConflictError) as race_error:
            winner = await self._find_existing(identity, request_fingerprint)
            if winner is not None:
                return winner
            if isinstance(race_error, TransactionConflictError):
                raise
            # A winner can expire or be removed between the conflict and lookup.
            # Do not execute the operation again inside this attempt.
            raise IdempotencyUnavailableError(
                "Durable winner is unavailable after the losing transaction rolled back"
            ) from race_error

        return IdempotencyResult(status=ExecutionStatus.EXECUTED, completed=completed)

    async def find_existing(
        self,
        identity: IdempotencyKey,
        request_fingerprint: bytes,
    ) -> IdempotencyResult | None:
        with self._exclusive_use():
            try:
                return await self._find_existing(identity, request_fingerprint)
            except PersistenceUnavailableError as error:
                raise IdempotencyUnavailableError(
                    "Durable lookup unavailable"
                ) from error

    async def _find_existing(
        self,
        identity: IdempotencyKey,
        request_fingerprint: bytes,
    ) -> IdempotencyResult | None:
        _validate_fingerprint(request_fingerprint)
        async with self._uow:
            existing = await self._durable_store.get_completed(identity)
        if existing is None or existing.expires_at <= self._clock():
            return None
        if existing.request_fingerprint != request_fingerprint:
            return IdempotencyResult(status=ExecutionStatus.CONFLICT)
        return IdempotencyResult(status=ExecutionStatus.REPLAY, completed=existing)


def _validate_fingerprint(request_fingerprint: bytes) -> None:
    if len(request_fingerprint) != 32:
        raise ValueError("request_fingerprint must be a full 32-byte SHA-256 digest")

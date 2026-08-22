from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Protocol

from app.application.exceptions.idempotency import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
    IdempotencyUnavailableError,
)
from app.application.idempotency.models import (
    ClaimStatus,
    CompletedIdempotencyResult,
    ExecutionStatus,
    IdempotencyKey,
    IdempotencyResult,
    StoredResult,
)
from app.application.idempotency.policy import IdempotencyMode, IdempotencyPolicy
from app.application.idempotency.transactional_execution import (
    TransactionalIdempotencyExecution,
)
from app.application.ports.idempotency.hot_store import HotIdempotencyStore
from app.application.ports.observability.idempotency_metrics import IdempotencyMetrics

IdempotentOperation = Callable[[], Awaitable[StoredResult]]


class AsyncSleeper(Protocol):
    async def sleep(self, seconds: float) -> None: ...


class _AsyncioSleeper:
    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class _NoOpIdempotencyMetrics:
    def observe_outcome(self, outcome: str) -> None:
        pass

    def observe_hot_degraded(self, stage: str) -> None:
        pass


class IdempotencyCoordinator:
    """
    Координатор распределенных блокировок в кэше и транзакционных защитных барьеров в БД.

    - Режим HOT_ONLY: быстрый путь через Redis с поведением fail-closed при недоступности хранилища.
    - Режим HOT_DURABLE: быстрый путь через Redis с бесшовной деградацией до транзакционной защиты в БД.
    """

    def __init__(
        self,
        hot_store: HotIdempotencyStore,
        durable_execution: TransactionalIdempotencyExecution | None = None,
        lease_token_factory: Callable[[], uuid.UUID] = uuid.uuid7,
        sleeper: AsyncSleeper | None = None,
        metrics: IdempotencyMetrics | None = None,
    ) -> None:
        self._hot_store = hot_store
        self._durable_execution = durable_execution
        self._lease_token_factory = lease_token_factory
        self._sleeper = sleeper or _AsyncioSleeper()
        self._metrics = metrics or _NoOpIdempotencyMetrics()

    @property
    def has_durable_execution(self) -> bool:
        """Флаг наличия настроенного компонента долговечного выполнения в БД."""
        return self._durable_execution is not None

    def supports_policy(self, policy: IdempotencyPolicy) -> bool:
        """Проверка поддержки заданной политики текущей конфигурацией координатора."""
        if policy.mode is IdempotencyMode.HOT_DURABLE:
            return self._durable_execution is not None
        return True

    async def execute(
        self,
        identity: IdempotencyKey,
        request_fingerprint: bytes,
        operation: IdempotentOperation,
        *,
        policy: IdempotencyPolicy,
    ) -> CompletedIdempotencyResult:
        """Координация выполнения операции согласно заданной политике идемпотентности."""
        # TODO слишком большое тело функции, думаю стоит разделить логику.
        # Особенно мне не нравятся проверки состояний if claim.status is ClaimStatus.REPLAY.
        # Можем ли мы использовать здесь паттерн Состояние (State)
        if len(request_fingerprint) != 32:
            raise ValueError(
                "Параметр request_fingerprint должен быть 32-байтным SHA-256 дайджестом"
            )
        if not self.supports_policy(policy):
            raise ValueError(
                "Для режима HOT_DURABLE необходимо настроить durable_execution"
            )

        lease_token = self._lease_token_factory()

        try:
            claim = await self._hot_store.claim(
                identity,
                request_fingerprint,
                lease_token,
                policy.lease_seconds,
            )
        except IdempotencyUnavailableError:  # TODO переименовать в HotStoreUnavailable
            self._metrics.observe_hot_degraded(
                "begin"
            )  # TODO Избавиться от строк - перейти на енамы
            if policy.mode is IdempotencyMode.HOT_ONLY:
                raise

            return await self._execute_durable(identity, request_fingerprint, operation)

        if claim.status is ClaimStatus.REPLAY:
            self._metrics.observe_outcome(
                "REPLAY"
            )  # TODO Избавиться от строк - перейти на енамы
            if claim.completed is None:
                raise RuntimeError(
                    "В ответе REPLAY отсутствуют данные завершенного результата"
                )
            return claim.completed

        if claim.status is ClaimStatus.CONFLICT:
            self._metrics.observe_outcome("CONFLICT")
            raise IdempotencyConflictError(
                "Ключ идемпотентности повторно использован с отличающимся телом запроса"
            )

        if claim.status is ClaimStatus.IN_PROGRESS:
            if self._durable_execution is not None:
                durable_result = await self._durable_execution.find_existing(
                    identity,
                    request_fingerprint,
                )
                if durable_result is not None:
                    if durable_result.status is ExecutionStatus.REPLAY:
                        self._metrics.observe_outcome("REPLAY")
                        if durable_result.completed is None:
                            raise RuntimeError(
                                "В ответе REPLAY отсутствуют данные завершенного результата"
                            )
                        return durable_result.completed
                    if durable_result.status is ExecutionStatus.CONFLICT:
                        self._metrics.observe_outcome("CONFLICT")
                        raise IdempotencyConflictError(
                            "Ключ идемпотентности повторно использован с отличающимся телом запроса"
                        )
            self._metrics.observe_outcome("IN_PROGRESS")
            raise IdempotencyInProgressError(
                "Запрос с данным ключом идемпотентности уже находится в процессе обработки"
            )

        # ClaimStatus.ACQUIRED -> Горячая блокировка успешно захвачена
        lost_lease = asyncio.Event()
        stop_heartbeat = asyncio.Event()
        heartbeat = asyncio.create_task(
            self._heartbeat(
                identity=identity,
                lease_token=lease_token,
                lease_seconds=policy.lease_seconds,
                lost_lease=lost_lease,
                stop=stop_heartbeat,
            )
        )

        try:
            if policy.mode is IdempotencyMode.HOT_DURABLE:
                assert self._durable_execution is not None  # проверено выше
                result = await self._durable_execution.execute_once(
                    identity,
                    request_fingerprint,
                    operation,
                )
            else:
                stored = await operation()
                completed = CompletedIdempotencyResult(
                    request_fingerprint=request_fingerprint,
                    **stored.model_dump(),
                )
                result = IdempotencyResult(
                    status=ExecutionStatus.EXECUTED,
                    completed=completed,
                )
        except BaseException:
            await self._stop_heartbeat(heartbeat, stop_heartbeat)
            if not lost_lease.is_set():
                try:
                    await self._hot_store.release(identity, lease_token)
                except IdempotencyUnavailableError:
                    self._metrics.observe_hot_degraded("release")
            raise

        await self._stop_heartbeat(heartbeat, stop_heartbeat)

        if lost_lease.is_set():
            self._metrics.observe_hot_degraded("lease")

        if (
            not lost_lease.is_set()
            and result.completed is not None
            and result.status in {ExecutionStatus.EXECUTED, ExecutionStatus.REPLAY}
        ):
            try:
                await self._hot_store.complete(
                    identity,
                    lease_token,
                    result.completed,
                )
            except IdempotencyUnavailableError:
                self._metrics.observe_hot_degraded("complete")
        elif not lost_lease.is_set():
            try:
                await self._hot_store.release(identity, lease_token)
            except IdempotencyUnavailableError:
                self._metrics.observe_hot_degraded("release")

        return self._evaluate_result(result)

    async def _execute_durable(
        self,
        identity: IdempotencyKey,
        request_fingerprint: bytes,
        operation: IdempotentOperation,
    ) -> CompletedIdempotencyResult:
        # TODO добавить docstring
        assert self._durable_execution is not None
        result = await self._durable_execution.execute_once(
            identity,
            request_fingerprint,
            operation,
        )
        return self._evaluate_result(result)

    def _evaluate_result(self, result: IdempotencyResult) -> CompletedIdempotencyResult:
        # TODO добавить docstring
        if result.status is ExecutionStatus.CONFLICT:
            self._metrics.observe_outcome("CONFLICT")
            raise IdempotencyConflictError(
                "Ключ идемпотентности повторно использован с отличающимся телом запроса"
            )
        if result.status is ExecutionStatus.IN_PROGRESS:
            self._metrics.observe_outcome("IN_PROGRESS")
            raise IdempotencyInProgressError(
                "Запрос с данным ключом идемпотентности уже находится в процессе обработки"
            )
        self._metrics.observe_outcome(result.status.value)
        if result.completed is None:
            raise RuntimeError(
                "Успешный результат идемпотентности не содержит завершенных данных"
            )
        return result.completed

    async def _heartbeat(
        self,
        *,
        identity: IdempotencyKey,
        lease_token: uuid.UUID,
        lease_seconds: int,
        lost_lease: asyncio.Event,
        stop: asyncio.Event,
    ) -> None:
        # TODO добавить docstring
        interval = lease_seconds / 3
        while not stop.is_set():
            try:
                await self._sleeper.sleep(interval)
                if stop.is_set():
                    return
                renewed = await self._hot_store.renew(
                    identity,
                    lease_token,
                    lease_seconds,
                )
            except asyncio.CancelledError:
                raise
            except IdempotencyUnavailableError:
                lost_lease.set()
                return
            except Exception:
                lost_lease.set()
                return
            if not renewed:
                lost_lease.set()
                return

    @staticmethod
    async def _stop_heartbeat(
        heartbeat: asyncio.Task[None],
        stop: asyncio.Event,
    ) -> None:
        # TODO добавить docstring
        stop.set()
        if not heartbeat.done():
            heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat

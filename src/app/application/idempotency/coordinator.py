from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timedelta
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
    HotDegradationStage,
    IdempotencyKey,
    IdempotencyResult,
)
from app.application.idempotency.policy import IdempotencyMode, IdempotencyPolicy
from app.application.ports.idempotency.durable_execution import (
    DurableExecution,
    IdempotentOperation,
)
from app.application.ports.idempotency.hot_store import HotIdempotencyStore
from app.application.ports.observability.idempotency_metrics import IdempotencyMetrics
from app.domain.clock import utc_now


class AsyncSleeper(Protocol):
    async def sleep(self, seconds: float) -> None: ...


class _AsyncioSleeper:
    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class _NoOpIdempotencyMetrics:
    def observe_outcome(self, outcome: ExecutionStatus) -> None:
        pass

    def observe_hot_degraded(self, stage: HotDegradationStage) -> None:
        pass


class IdempotencyCoordinator:
    """Coordinate leases and replay without knowing command routing or SQL.

    HOT_ONLY relies on volatile storage for both coordination and replay.
    HOT_DURABLE delegates commit safety to DurableExecution.
    """

    def __init__(
        self,
        hot_store: HotIdempotencyStore,
        durable_execution: DurableExecution | None = None,
        lease_token_factory: Callable[[], uuid.UUID] = uuid.uuid7,
        sleeper: AsyncSleeper | None = None,
        metrics: IdempotencyMetrics | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._clock = clock
        self._hot_store = hot_store
        self._durable_execution = durable_execution
        self._lease_token_factory = lease_token_factory
        self._sleeper = sleeper or _AsyncioSleeper()
        self._metrics = metrics or _NoOpIdempotencyMetrics()

    def supports_policy(self, policy: IdempotencyPolicy) -> bool:
        return (
            policy.mode is IdempotencyMode.HOT_ONLY
            or self._durable_execution is not None
        )

    async def execute(
        self,
        identity: IdempotencyKey,
        request_fingerprint: bytes,
        operation: IdempotentOperation,
        *,
        policy: IdempotencyPolicy,
    ) -> CompletedIdempotencyResult:
        """Return the authoritative result or raise an application exception."""
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
        except IdempotencyUnavailableError:
            self._metrics.observe_hot_degraded(HotDegradationStage.BEGIN)
            if policy.mode is IdempotencyMode.HOT_ONLY:
                raise
            return self._evaluate_result(
                await self._execute_durable(
                    identity, request_fingerprint, operation, policy.retention_seconds
                )
            )

        match claim.status:
            case ClaimStatus.REPLAY:
                return self._evaluate_result(
                    IdempotencyResult(
                        status=ExecutionStatus.REPLAY,
                        completed=claim.completed,
                    )
                )
            case ClaimStatus.CONFLICT | ClaimStatus.IN_PROGRESS:
                return await self._resolve_busy(
                    identity,
                    request_fingerprint,
                    claim.status,
                    policy,
                )
            case ClaimStatus.ACQUIRED:
                return await self._execute_claimed(
                    identity,
                    request_fingerprint,
                    lease_token,
                    operation,
                    policy,
                )
        raise RuntimeError("Unsupported hot claim status")

    async def _resolve_busy(
        self,
        identity: IdempotencyKey,
        request_fingerprint: bytes,
        status: ClaimStatus,
        policy: IdempotencyPolicy,
    ) -> CompletedIdempotencyResult:
        """A committed durable winner takes precedence over a pending hot lease."""
        if policy.mode is IdempotencyMode.HOT_DURABLE:
            assert self._durable_execution is not None
            existing = await self._durable_execution.find_existing(
                identity, request_fingerprint
            )
            if existing is not None:
                return self._evaluate_result(existing)
        outcome = (
            ExecutionStatus.CONFLICT
            if status is ClaimStatus.CONFLICT
            else ExecutionStatus.IN_PROGRESS
        )
        return self._evaluate_result(IdempotencyResult(status=outcome))

    async def _execute_claimed(
        self,
        identity: IdempotencyKey,
        request_fingerprint: bytes,
        lease_token: uuid.UUID,
        operation: IdempotentOperation,
        policy: IdempotencyPolicy,
    ) -> CompletedIdempotencyResult:
        """Keep the lease alive around execution; only its owner may complete it."""
        lost_lease = asyncio.Event()
        stop = asyncio.Event()
        heartbeat = asyncio.create_task(
            self._heartbeat(
                identity=identity,
                lease_token=lease_token,
                lease_seconds=policy.lease_seconds,
                lost_lease=lost_lease,
                stop=stop,
            )
        )
        try:
            if policy.mode is IdempotencyMode.HOT_DURABLE:
                result = await self._execute_durable(
                    identity, request_fingerprint, operation, policy.retention_seconds
                )
            else:
                stored = await operation()
                result = IdempotencyResult(
                    status=ExecutionStatus.EXECUTED,
                    completed=CompletedIdempotencyResult(
                        request_fingerprint=request_fingerprint,
                        expires_at=self._clock()
                        + timedelta(seconds=policy.retention_seconds),
                        **stored.model_dump(),
                    ),
                )
        except BaseException:
            if not lost_lease.is_set():
                await self._release(identity, lease_token)
            raise
        finally:
            await self._stop_heartbeat(heartbeat, stop)

        if lost_lease.is_set():
            self._metrics.observe_hot_degraded(HotDegradationStage.LEASE)
            if policy.mode is IdempotencyMode.HOT_ONLY:
                raise IdempotencyUnavailableError(
                    "Hot lease lost; the business effect may already have happened"
                )
        elif result.completed is not None:
            await self._complete(identity, lease_token, result.completed, policy)
        else:
            await self._release(identity, lease_token)
        return self._evaluate_result(result)

    async def _execute_durable(
        self,
        identity: IdempotencyKey,
        request_fingerprint: bytes,
        operation: IdempotentOperation,
        retention_seconds: int,
    ) -> IdempotencyResult:
        """Use the configured atomic execution capability, without storage details."""
        assert self._durable_execution is not None
        return await self._durable_execution.execute_once(
            identity,
            request_fingerprint,
            operation,
            retention_seconds=retention_seconds,
        )

    async def _complete(
        self,
        identity: IdempotencyKey,
        lease_token: uuid.UUID,
        completed: CompletedIdempotencyResult,
        policy: IdempotencyPolicy,
    ) -> None:
        """Hot publication failure cannot undo an already committed business effect."""
        try:
            published = await self._hot_store.complete(
                identity,
                lease_token,
                completed,
                cache_ttl_seconds=policy.hot_result_ttl_seconds,
            )
        except IdempotencyUnavailableError:
            self._metrics.observe_hot_degraded(HotDegradationStage.COMPLETE)
            if policy.mode is IdempotencyMode.HOT_ONLY:
                raise
            return
        if not published:
            self._metrics.observe_hot_degraded(
                HotDegradationStage.LEASE_LOST_ON_COMPLETE
            )
            if policy.mode is IdempotencyMode.HOT_ONLY:
                raise IdempotencyUnavailableError(
                    "Hot result not saved; the business effect may already have happened"
                )

    async def _release(self, identity: IdempotencyKey, lease_token: uuid.UUID) -> None:
        """Best-effort owner-checked cleanup; a false CAS is a lost lease."""
        try:
            released = await self._hot_store.release(identity, lease_token)
        except IdempotencyUnavailableError:
            self._metrics.observe_hot_degraded(HotDegradationStage.RELEASE)
        else:
            if not released:
                self._metrics.observe_hot_degraded(
                    HotDegradationStage.LEASE_LOST_ON_RELEASE
                )

    def _evaluate_result(self, result: IdempotencyResult) -> CompletedIdempotencyResult:
        """Hide execution decisions from middleware and its callers."""
        self._metrics.observe_outcome(result.status)
        if result.status is ExecutionStatus.CONFLICT:
            raise IdempotencyConflictError(
                "Ключ идемпотентности повторно использован с отличающимся телом запроса"
            )
        if result.status is ExecutionStatus.IN_PROGRESS:
            raise IdempotencyInProgressError(
                "Запрос с данным ключом идемпотентности уже находится в процессе обработки"
            )
        if result.completed is None:
            raise RuntimeError("Successful idempotency outcome has no completed result")
        if result.completed.expires_at <= self._clock():
            raise IdempotencyUnavailableError("Replay lifetime expired before response")
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
        """Renew ownership until stopped; renewal failure invalidates local ownership."""
        while not stop.is_set():
            try:
                await self._sleeper.sleep(lease_seconds / 3)
                if stop.is_set():
                    return
                renewed = await self._hot_store.renew(
                    identity, lease_token, lease_seconds
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                lost_lease.set()
                return
            if not renewed:
                lost_lease.set()
                return

    @staticmethod
    async def _stop_heartbeat(
        heartbeat: asyncio.Task[None], stop: asyncio.Event
    ) -> None:
        """Cancel and join the owned background task before returning."""
        stop.set()
        if not heartbeat.done():
            heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat

from uuid import UUID

from app.application.exceptions.idempotency import IdempotencyUnavailableError
from app.application.idempotency.models import (
    ClaimResult,
    CompletedIdempotencyResult,
    IdempotencyKey,
)
from app.application.ports.idempotency.hot_store import HotIdempotencyStore
from app.infrastructure.resilience import CircuitBreakerError, IdempotencyCircuitBreaker


class CircuitBreakingHotStore:
    """Декоратор HotIdempotencyStore с защитой от каскадных сбоев через Circuit Breaker."""

    def __init__(
        self,
        inner: HotIdempotencyStore,
        circuit_breaker: IdempotencyCircuitBreaker,
    ) -> None:
        self._inner = inner
        self._circuit_breaker = circuit_breaker

    async def claim(
        self,
        identity: IdempotencyKey,
        request_fingerprint: bytes,
        lease_token: UUID,
        lease_seconds: int,
    ) -> ClaimResult:
        try:
            return await self._circuit_breaker.call(
                self._inner.claim,
                identity,
                request_fingerprint,
                lease_token,
                lease_seconds,
            )
        except CircuitBreakerError as error:
            raise IdempotencyUnavailableError(
                "Предохранитель горячего хранилища находится в состоянии OPEN"
            ) from error

    async def renew(
        self,
        identity: IdempotencyKey,
        lease_token: UUID,
        lease_seconds: int,
    ) -> bool:
        try:
            return await self._circuit_breaker.call(
                self._inner.renew,
                identity,
                lease_token,
                lease_seconds,
            )
        except CircuitBreakerError as error:
            raise IdempotencyUnavailableError(
                "Предохранитель горячего хранилища находится в состоянии OPEN"
            ) from error

    async def complete(
        self,
        identity: IdempotencyKey,
        lease_token: UUID,
        result: CompletedIdempotencyResult,
    ) -> bool:
        try:
            return await self._circuit_breaker.call(
                self._inner.complete,
                identity,
                lease_token,
                result,
            )
        except CircuitBreakerError as error:
            raise IdempotencyUnavailableError(
                "Предохранитель горячего хранилища находится в состоянии OPEN"
            ) from error

    async def release(
        self,
        identity: IdempotencyKey,
        lease_token: UUID,
    ) -> bool:
        try:
            return await self._circuit_breaker.call(
                self._inner.release,
                identity,
                lease_token,
            )
        except CircuitBreakerError as error:
            raise IdempotencyUnavailableError(
                "Предохранитель горячего хранилища находится в состоянии OPEN"
            ) from error

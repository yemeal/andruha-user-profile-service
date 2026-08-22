import uuid

import pytest

from app.application.exceptions.idempotency import IdempotencyUnavailableError
from app.application.idempotency.fingerprint import (
    compute_key_digest,
    compute_request_fingerprint,
)
from app.application.idempotency.models import (
    ClaimResult,
    ClaimStatus,
    CompletedIdempotencyResult,
    IdempotencyKey,
)
from app.infrastructure.idempotency.redis.circuit_breaking_hot_store import (
    CircuitBreakingHotStore,
)
from app.infrastructure.resilience.circuit_breaker import (
    CircuitBreakerError,
    IdempotencyCircuitBreaker,
)


class RecordingCircuitBreaker(IdempotencyCircuitBreaker):
    def __init__(self, error: Exception | None = None) -> None:
        super().__init__(fail_max=3, recovery_timeout=10.0, name="test_cb")
        self.forced_error = error

    async def call(self, func, *args, **kwargs):
        if self.forced_error is not None:
            raise self.forced_error
        return await func(*args, **kwargs)


class FakeInnerStore:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def claim(
        self, identity, request_fingerprint, lease_token, lease_seconds
    ) -> ClaimResult:
        self.calls.append("claim")
        return ClaimResult(status=ClaimStatus.ACQUIRED)

    async def renew(self, identity, lease_token, lease_seconds) -> bool:
        self.calls.append("renew")
        return True

    async def complete(self, identity, lease_token, result) -> bool:
        self.calls.append("complete")
        return True

    async def release(self, identity, lease_token) -> bool:
        self.calls.append("release")
        return True


def _identity() -> IdempotencyKey:
    return IdempotencyKey(
        subject_id="user-1",
        operation="update",
        key_digest=compute_key_digest("k"),
    )


async def test_circuit_breaking_store_passes_calls():
    inner = FakeInnerStore()
    cb = RecordingCircuitBreaker()
    store = CircuitBreakingHotStore(inner, cb)

    identity = _identity()
    fp = compute_request_fingerprint({"k": "v"})
    token = uuid.uuid4()

    res = await store.claim(identity, fp, token, 30)
    assert res.status == ClaimStatus.ACQUIRED

    await store.renew(identity, token, 30)
    await store.complete(
        identity,
        token,
        CompletedIdempotencyResult(
            result_type="t",
            result_payload={},
            request_fingerprint=fp,
        ),
    )
    await store.release(identity, token)

    assert inner.calls == ["claim", "renew", "complete", "release"]


async def test_open_circuit_breaker_maps_to_unavailable():
    inner = FakeInnerStore()
    cb = RecordingCircuitBreaker(error=CircuitBreakerError("Circuit is OPEN"))
    store = CircuitBreakingHotStore(inner, cb)

    with pytest.raises(IdempotencyUnavailableError, match="состоянии OPEN"):
        await store.claim(
            _identity(), compute_request_fingerprint({"k": "v"}), uuid.uuid4(), 30
        )

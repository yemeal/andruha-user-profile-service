import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.application.exceptions.idempotency import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
    IdempotencyUnavailableError,
)
from app.application.idempotency.coordinator import IdempotencyCoordinator
from app.application.idempotency.fingerprint import (
    compute_key_digest,
    compute_request_fingerprint,
)
from app.application.idempotency.models import (
    ClaimResult,
    ClaimStatus,
    CompletedIdempotencyResult,
    ExecutionStatus,
    IdempotencyKey,
    IdempotencyResult,
    StoredResult,
)
from app.application.idempotency.policy import IdempotencyMode, IdempotencyPolicy


@dataclass
class FakeHotStore:
    claim_results: list[ClaimResult] = field(
        default_factory=lambda: [ClaimResult(status=ClaimStatus.ACQUIRED)]
    )
    claim_error: Exception | None = None
    renew_result: bool = True
    renew_error: Exception | None = None
    complete_result: bool = True
    release_result: bool = True
    claim_calls: list[tuple[Any, ...]] = field(default_factory=list)
    renew_calls: list[tuple[Any, ...]] = field(default_factory=list)
    complete_calls: list[tuple[Any, ...]] = field(default_factory=list)
    release_calls: list[tuple[Any, ...]] = field(default_factory=list)

    async def claim(
        self,
        identity: IdempotencyKey,
        request_fingerprint: bytes,
        lease_token: uuid.UUID,
        lease_seconds: int,
    ) -> ClaimResult:
        self.claim_calls.append(
            (identity, request_fingerprint, lease_token, lease_seconds)
        )
        if self.claim_error is not None:
            raise self.claim_error
        return self.claim_results.pop(0)

    async def renew(
        self,
        identity: IdempotencyKey,
        lease_token: uuid.UUID,
        lease_seconds: int,
    ) -> bool:
        self.renew_calls.append((identity, lease_token, lease_seconds))
        if self.renew_error is not None:
            raise self.renew_error
        return self.renew_result

    async def complete(
        self,
        identity: IdempotencyKey,
        lease_token: uuid.UUID,
        result: CompletedIdempotencyResult,
    ) -> bool:
        self.complete_calls.append((identity, lease_token, result))
        return self.complete_result

    async def release(
        self,
        identity: IdempotencyKey,
        lease_token: uuid.UUID,
    ) -> bool:
        self.release_calls.append((identity, lease_token))
        return self.release_result


@dataclass
class FakeDurableExecution:
    find_result: IdempotencyResult | None = None
    execute_result: IdempotencyResult | None = None
    execute_calls: list[tuple[IdempotencyKey, bytes]] = field(default_factory=list)

    async def find_existing(
        self, identity: IdempotencyKey, request_fingerprint: bytes
    ) -> IdempotencyResult | None:
        return self.find_result

    async def execute_once(
        self, identity: IdempotencyKey, request_fingerprint: bytes, operation: Any
    ) -> IdempotencyResult:
        self.execute_calls.append((identity, request_fingerprint))
        if self.execute_result is not None:
            return self.execute_result
        stored = await operation()
        completed = CompletedIdempotencyResult(
            request_fingerprint=request_fingerprint,
            **stored.model_dump(),
        )
        return IdempotencyResult(
            status=ExecutionStatus.EXECUTED,
            completed=completed,
        )


def _identity() -> IdempotencyKey:
    return IdempotencyKey(
        subject_id="user-1",
        operation="update_profile",
        key_digest=compute_key_digest("idemp-key-1"),
    )


def _fingerprint() -> bytes:
    return compute_request_fingerprint({"display_name": "Alex"})


def _stored() -> StoredResult:
    return StoredResult(
        result_type="profile",
        result_payload={"display_name": "Alex"},
        result_version=1,
        resource_type="profile",
        resource_id=str(uuid.uuid4()),
        resource_version=1,
    )


async def test_hot_only_successful_execution():
    hot = FakeHotStore()
    coordinator = IdempotencyCoordinator(hot_store=hot)
    policy = IdempotencyPolicy(mode=IdempotencyMode.HOT_ONLY, lease_seconds=30)
    identity = _identity()
    fp = _fingerprint()
    stored = _stored()

    res = await coordinator.execute(
        identity,
        fp,
        lambda: asyncio.sleep(0, result=stored),
        policy=policy,
    )

    assert res.request_fingerprint == fp
    assert res.result_payload == stored.result_payload
    assert len(hot.claim_calls) == 1
    assert len(hot.complete_calls) == 1


async def test_hot_only_fails_closed_when_hot_store_unavailable():
    hot = FakeHotStore(claim_error=IdempotencyUnavailableError("Redis down"))
    coordinator = IdempotencyCoordinator(hot_store=hot)
    policy = IdempotencyPolicy(mode=IdempotencyMode.HOT_ONLY, lease_seconds=30)

    with pytest.raises(IdempotencyUnavailableError):
        await coordinator.execute(
            _identity(),
            _fingerprint(),
            lambda: asyncio.sleep(0, result=_stored()),
            policy=policy,
        )


async def test_hot_durable_graceful_degradation_on_hot_store_failure():
    hot = FakeHotStore(claim_error=IdempotencyUnavailableError("Redis down"))
    durable = FakeDurableExecution()
    coordinator = IdempotencyCoordinator(hot_store=hot, durable_execution=durable)
    policy = IdempotencyPolicy(mode=IdempotencyMode.HOT_DURABLE, lease_seconds=30)
    identity = _identity()
    fp = _fingerprint()
    stored = _stored()

    res = await coordinator.execute(
        identity,
        fp,
        lambda: asyncio.sleep(0, result=stored),
        policy=policy,
    )

    assert res.request_fingerprint == fp
    assert len(durable.execute_calls) == 1
    assert len(hot.complete_calls) == 0


async def test_hot_durable_requires_durable_execution():
    hot = FakeHotStore()
    coordinator = IdempotencyCoordinator(hot_store=hot, durable_execution=None)
    policy = IdempotencyPolicy(mode=IdempotencyMode.HOT_DURABLE, lease_seconds=30)

    with pytest.raises(
        ValueError,
        match="Для режима HOT_DURABLE необходимо настроить durable_execution",
    ):
        await coordinator.execute(
            _identity(),
            _fingerprint(),
            lambda: asyncio.sleep(0, result=_stored()),
            policy=policy,
        )


async def test_conflict_raises_exception():
    hot = FakeHotStore(claim_results=[ClaimResult(status=ClaimStatus.CONFLICT)])
    coordinator = IdempotencyCoordinator(hot_store=hot)
    policy = IdempotencyPolicy(mode=IdempotencyMode.HOT_ONLY, lease_seconds=30)

    with pytest.raises(IdempotencyConflictError):
        await coordinator.execute(
            _identity(),
            _fingerprint(),
            lambda: asyncio.sleep(0, result=_stored()),
            policy=policy,
        )


async def test_in_progress_raises_exception():
    hot = FakeHotStore(claim_results=[ClaimResult(status=ClaimStatus.IN_PROGRESS)])
    coordinator = IdempotencyCoordinator(hot_store=hot)
    policy = IdempotencyPolicy(mode=IdempotencyMode.HOT_ONLY, lease_seconds=30)

    with pytest.raises(IdempotencyInProgressError):
        await coordinator.execute(
            _identity(),
            _fingerprint(),
            lambda: asyncio.sleep(0, result=_stored()),
            policy=policy,
        )


async def test_replay_returns_cached_completed_result():
    stored = _stored()
    fp = _fingerprint()
    completed = CompletedIdempotencyResult(
        request_fingerprint=fp,
        **stored.model_dump(),
    )
    hot = FakeHotStore(
        claim_results=[ClaimResult(status=ClaimStatus.REPLAY, completed=completed)]
    )
    coordinator = IdempotencyCoordinator(hot_store=hot)
    policy = IdempotencyPolicy(mode=IdempotencyMode.HOT_ONLY, lease_seconds=30)

    op_called = False

    async def op():
        nonlocal op_called
        op_called = True
        return stored

    res = await coordinator.execute(_identity(), fp, op, policy=policy)

    assert res == completed
    assert op_called is False


async def test_operation_failure_releases_lease():
    hot = FakeHotStore()
    coordinator = IdempotencyCoordinator(hot_store=hot)
    policy = IdempotencyPolicy(mode=IdempotencyMode.HOT_ONLY, lease_seconds=30)

    async def op():
        raise RuntimeError("handler failed")

    with pytest.raises(RuntimeError, match="handler failed"):
        await coordinator.execute(_identity(), _fingerprint(), op, policy=policy)

    assert len(hot.release_calls) == 1
    assert len(hot.complete_calls) == 0

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.application.idempotency.fingerprint import (
    compute_key_digest,
    compute_request_fingerprint,
)
from app.application.idempotency.models import (
    CompletedIdempotencyResult,
    ExecutionStatus,
    IdempotencyKey,
    StoredResult,
)
from app.application.idempotency.transactional_execution import (
    TransactionalIdempotencyExecution,
)


@dataclass
class FakeTransactionalSession:
    effects: list[dict[str, Any]] = field(default_factory=list)
    records: dict[IdempotencyKey, CompletedIdempotencyResult] = field(
        default_factory=dict
    )
    pending_effects: list[dict[str, Any]] = field(default_factory=list)
    pending_records: dict[IdempotencyKey, CompletedIdempotencyResult] = field(
        default_factory=dict
    )
    commits: int = 0
    rollbacks: int = 0
    in_transaction: bool = False

    def stage_effect(self, effect: dict[str, Any]) -> None:
        self.pending_effects.append(effect)

    def commit(self) -> None:
        self.effects.extend(self.pending_effects)
        self.records.update(self.pending_records)
        self.pending_effects.clear()
        self.pending_records.clear()
        self.commits += 1

    def rollback(self) -> None:
        self.pending_effects.clear()
        self.pending_records.clear()
        self.rollbacks += 1


class FakeUOW:
    def __init__(self, session: FakeTransactionalSession) -> None:
        self._session = session

    async def __aenter__(self) -> FakeUOW:
        self._session.in_transaction = True
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        try:
            if exc_type is None:
                self._session.commit()
            else:
                self._session.rollback()
        finally:
            self._session.in_transaction = False


class FakeDurableStore:
    def __init__(self, session: FakeTransactionalSession) -> None:
        self._session = session
        self.conflict_on_add: CompletedIdempotencyResult | None = None

    async def get_completed(
        self, identity: IdempotencyKey
    ) -> CompletedIdempotencyResult | None:
        self._session.in_transaction = True
        return self._session.pending_records.get(identity) or self._session.records.get(
            identity
        )

    async def try_add_completed(
        self, identity: IdempotencyKey, completed: CompletedIdempotencyResult
    ) -> bool:
        if self.conflict_on_add is not None:
            self._session.records[identity] = self.conflict_on_add
            self.conflict_on_add = None
            return False
        if identity in self._session.records:
            return False
        self._session.pending_records[identity] = completed
        return True


def _identity() -> IdempotencyKey:
    return IdempotencyKey(
        subject_id="user-1",
        operation="update_profile",
        key_digest=compute_key_digest("test-key-1"),
    )


def _fingerprint(version: int = 1) -> bytes:
    return compute_request_fingerprint({"version": version})


def _stored() -> StoredResult:
    return StoredResult(
        result_type="profile",
        result_payload={"display_name": "Alex"},
        result_version=1,
        resource_type="profile",
        resource_id=str(uuid.uuid4()),
        resource_version=1,
    )


async def test_atomic_execution_and_commit():
    session = FakeTransactionalSession()
    store = FakeDurableStore(session)
    uow = FakeUOW(session)
    execution = TransactionalIdempotencyExecution(store, uow)

    identity = _identity()
    fp = _fingerprint()
    stored = _stored()

    async def operation():
        session.stage_effect({"action": "updated"})
        return stored

    res = await execution.execute_once(identity, fp, operation)

    assert res.status == ExecutionStatus.EXECUTED
    assert res.completed is not None
    assert res.completed.request_fingerprint == fp
    assert len(session.effects) == 1
    assert session.commits == 2  # 1 read-check + 1 write
    assert session.rollbacks == 0


async def test_operation_failure_rolls_back():
    session = FakeTransactionalSession()
    store = FakeDurableStore(session)
    uow = FakeUOW(session)
    execution = TransactionalIdempotencyExecution(store, uow)

    identity = _identity()
    fp = _fingerprint()

    async def operation():
        session.stage_effect({"action": "updated"})
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await execution.execute_once(identity, fp, operation)

    assert len(session.effects) == 0
    assert len(session.records) == 0
    assert session.rollbacks == 1


async def test_replay_existing():
    session = FakeTransactionalSession()
    store = FakeDurableStore(session)
    uow = FakeUOW(session)
    execution = TransactionalIdempotencyExecution(store, uow)

    identity = _identity()
    fp = _fingerprint()
    stored = _stored()
    completed = CompletedIdempotencyResult(
        request_fingerprint=fp,
        **stored.model_dump(),
    )
    session.records[identity] = completed

    op_called = False

    async def operation():
        nonlocal op_called
        op_called = True
        return stored

    res = await execution.execute_once(identity, fp, operation)

    assert res.status == ExecutionStatus.REPLAY
    assert res.completed == completed
    assert op_called is False


async def test_conflict_existing():
    session = FakeTransactionalSession()
    store = FakeDurableStore(session)
    uow = FakeUOW(session)
    execution = TransactionalIdempotencyExecution(store, uow)

    identity = _identity()
    fp1 = _fingerprint(1)
    fp2 = _fingerprint(2)
    stored = _stored()
    completed = CompletedIdempotencyResult(
        request_fingerprint=fp1,
        **stored.model_dump(),
    )
    session.records[identity] = completed

    res = await execution.execute_once(
        identity, fp2, lambda: asyncio.sleep(0, result=stored)
    )

    assert res.status == ExecutionStatus.CONFLICT
    assert res.completed is None

import re
import uuid
from typing import Any, cast

import pytest
import redis.exceptions
from redis.asyncio import Redis

from app.application.exceptions.idempotency import IdempotencyUnavailableError
from app.application.idempotency.fingerprint import (
    compute_key_digest,
    compute_request_fingerprint,
)
from app.application.idempotency.models import (
    ClaimStatus,
    CompletedIdempotencyResult,
    IdempotencyKey,
)
from app.infrastructure.idempotency.redis.hot_store import RedisHotIdempotencyStore


class FakeEvalRedis:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[Any, ...]] = []

    async def eval(self, *arguments: Any) -> Any:
        self.calls.append(arguments)
        res = self.responses.pop(0)
        if isinstance(res, BaseException):
            raise res
        return res


def _identity() -> IdempotencyKey:
    return IdempotencyKey(
        subject_id="user-123",
        operation="update_profile",
        key_digest=compute_key_digest("secret-key"),
    )


def _store(fake: FakeEvalRedis) -> RedisHotIdempotencyStore:
    return RedisHotIdempotencyStore(
        cast(Redis, fake),
        result_ttl_seconds=3600,
        key_namespace="test:profile:idempotency",
    )


async def test_claim_terminal_codes():
    fake = FakeEvalRedis([[1], [3], [4]])
    store = _store(fake)
    identity = _identity()
    fp = compute_request_fingerprint({"key": "val"})

    res1 = await store.claim(identity, fp, uuid.uuid4(), 60)
    assert res1.status == ClaimStatus.ACQUIRED

    res2 = await store.claim(identity, fp, uuid.uuid4(), 60)
    assert res2.status == ClaimStatus.CONFLICT

    res3 = await store.claim(identity, fp, uuid.uuid4(), 60)
    assert res3.status == ClaimStatus.IN_PROGRESS


async def test_claim_replay():
    fp = compute_request_fingerprint({"key": "val"})
    completed = CompletedIdempotencyResult(
        result_type="profile",
        result_payload={"display_name": "Alex"},
        result_version=1,
        request_fingerprint=fp,
    )
    encoded = RedisHotIdempotencyStore._encode_completed(completed)
    fake = FakeEvalRedis([[2, encoded.encode("utf-8")]])
    store = _store(fake)

    res = await store.claim(_identity(), fp, uuid.uuid4(), 60)
    assert res.status == ClaimStatus.REPLAY
    assert res.completed is not None
    assert res.completed.request_fingerprint == fp
    assert res.completed.result_payload == {"display_name": "Alex"}


async def test_storage_key_privacy():
    fake = FakeEvalRedis([[1]])
    store = _store(fake)
    identity = _identity()
    fp = compute_request_fingerprint({"key": "val"})

    await store.claim(identity, fp, uuid.uuid4(), 60)

    storage_key = fake.calls[0][2]
    assert re.fullmatch(r"test:profile:idempotency:[0-9a-f]{64}", storage_key)
    assert identity.subject_id not in storage_key
    assert identity.operation not in storage_key
    assert "secret-key" not in storage_key


async def test_redis_error_mapping_to_unavailable():
    fake = FakeEvalRedis([redis.exceptions.ConnectionError("Redis connection lost")])
    store = _store(fake)

    with pytest.raises(IdempotencyUnavailableError):
        await store.claim(
            _identity(), compute_request_fingerprint({"k": "v"}), uuid.uuid4(), 60
        )

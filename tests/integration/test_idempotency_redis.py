"""Redis script contract checks. TEST_IDEMPOTENCY_REDIS_URL must target a test Redis."""

import os
from datetime import timedelta
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from app.application.idempotency.models import (
    ClaimStatus,
    CompletedIdempotencyResult,
    IdempotencyKey,
)
from app.domain.clock import utc_now
from app.infrastructure.idempotency.redis.hot_store import RedisHotIdempotencyStore

pytestmark = pytest.mark.integration


@pytest.fixture
async def redis_store():
    url = os.getenv("TEST_IDEMPOTENCY_REDIS_URL")
    if not url:
        pytest.skip("TEST_IDEMPOTENCY_REDIS_URL is not configured")
    client = Redis.from_url(url)
    namespace = "idempotency-test:" + uuid4().hex
    store = RedisHotIdempotencyStore(client, key_namespace=namespace)
    try:
        yield client, store
    finally:
        # Delete only keys in the unique namespace created by this test.
        async for key in client.scan_iter(match=namespace + ":*"):
            await client.delete(key)
        await client.aclose()


@pytest.mark.parametrize("completion_only", [False, True])
async def test_complete_caps_cache_ttl_to_absolute_replay_deadline(
    redis_store, completion_only
):
    client, store = redis_store
    identity = IdempotencyKey(subject_id="user:1", operation="op", key_digest=b"k" * 32)
    owner = uuid4()
    assert (
        await store.claim(identity, b"f" * 32, owner, 30)
    ).status is ClaimStatus.ACQUIRED
    result = CompletedIdempotencyResult(
        result_type="completion" if completion_only else "snapshot",
        result_payload=None if completion_only else {"value": 1},
        request_fingerprint=b"f" * 32,
        expires_at=utc_now() + timedelta(seconds=3),
    )
    assert await store.complete(identity, owner, result, cache_ttl_seconds=3600)
    ttl = await client.pttl(store._storage_key(identity))
    assert 0 < ttl <= 3000
    replay = await store.claim(identity, b"f" * 32, uuid4(), 30)
    assert replay.completed == result
    assert not await store.release(identity, owner)


async def test_expired_result_is_not_published_and_stale_owner_cannot_release(
    redis_store,
):
    _, store = redis_store
    identity = IdempotencyKey(subject_id="user:1", operation="op", key_digest=b"k" * 32)
    old_owner, new_owner = uuid4(), uuid4()
    await store.claim(identity, b"f" * 32, old_owner, 30)
    expired = CompletedIdempotencyResult(
        result_type="snapshot",
        result_payload={"value": 1},
        request_fingerprint=b"f" * 32,
        expires_at=utc_now() - timedelta(seconds=1),
    )
    assert not await store.complete(identity, old_owner, expired, cache_ttl_seconds=30)
    assert (
        await store.claim(identity, b"f" * 32, new_owner, 30)
    ).status is ClaimStatus.ACQUIRED
    assert not await store.release(identity, old_owner)
    assert (
        await store.claim(identity, b"f" * 32, uuid4(), 30)
    ).status is ClaimStatus.IN_PROGRESS

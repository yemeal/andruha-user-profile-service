import uuid

import pytest
from pydantic import ValidationError

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


def test_idempotency_key_validation():
    digest = b"a" * 32
    key = IdempotencyKey(
        subject_id="user-123",
        operation="update_profile",
        key_digest=digest,
    )
    assert key.subject_id == "user-123"
    assert key.operation == "update_profile"
    assert key.key_digest == digest

    with pytest.raises(ValidationError):
        IdempotencyKey(subject_id="", operation="op", key_digest=digest)

    with pytest.raises(ValidationError):
        IdempotencyKey(subject_id="user", operation="op", key_digest=b"short")


def test_stored_result_validation():
    res_id = uuid.uuid4()
    stored = StoredResult(
        result_type="profile_dto",
        result_payload={"display_name": "Alex"},
        result_version=1,
        resource_type="profile",
        resource_id=res_id,
        resource_version=1,
    )
    assert stored.resource_id == str(res_id)

    # Missing resource_id when resource_type given
    with pytest.raises(ValueError, match="resource_type и resource_id"):
        StoredResult(
            result_type="profile_dto",
            resource_type="profile",
            resource_id=None,
        )

    # Missing payload and resource_id
    with pytest.raises(ValueError, match="ссылки на ресурс"):
        StoredResult(result_type="empty")


def test_claim_result_validation():
    fingerprint = b"b" * 32
    completed = CompletedIdempotencyResult(
        result_type="test",
        result_payload={"data": 1},
        request_fingerprint=fingerprint,
    )

    replay_claim = ClaimResult(
        status=ClaimStatus.REPLAY,
        completed=completed,
    )
    assert replay_claim.status == ClaimStatus.REPLAY
    assert replay_claim.completed == completed

    with pytest.raises(ValueError, match="REPLAY"):
        ClaimResult(status=ClaimStatus.REPLAY, completed=None)

    with pytest.raises(ValueError, match="REPLAY"):
        ClaimResult(status=ClaimStatus.ACQUIRED, completed=completed)


def test_idempotency_result_validation():
    completed = CompletedIdempotencyResult(
        result_type="test",
        result_payload={"data": 1},
        request_fingerprint=b"c" * 32,
    )

    res = IdempotencyResult(
        status=ExecutionStatus.EXECUTED,
        completed=completed,
    )
    assert res.status == ExecutionStatus.EXECUTED

    with pytest.raises(ValueError, match="Статус выполнения"):
        IdempotencyResult(status=ExecutionStatus.EXECUTED, completed=None)


def test_policy_defaults_and_validation():
    policy = IdempotencyPolicy()
    assert policy.mode == IdempotencyMode.HOT_DURABLE
    assert policy.lease_seconds == 30

    hot_policy = IdempotencyPolicy(
        mode=IdempotencyMode.HOT_ONLY,
        lease_seconds=15,
    )
    assert hot_policy.mode == IdempotencyMode.HOT_ONLY
    assert hot_policy.lease_seconds == 15

    with pytest.raises(ValidationError):
        IdempotencyPolicy(lease_seconds=0)

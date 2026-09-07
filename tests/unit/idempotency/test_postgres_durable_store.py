import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects.postgresql import dialect

from app.application.idempotency.models import (
    CompletedIdempotencyResult,
    IdempotencyKey,
)
from app.domain.clock import utc_now
from app.infrastructure.idempotency.postgres.durable_store import (
    PostgresDurableIdempotencyStore,
)


@pytest.mark.parametrize("inserted", [True, False])
async def test_write_uses_conditional_expiry_replacement_and_json_safe_payload(
    inserted,
):
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                scalar_one_or_none=lambda: uuid4() if inserted else None
            )
        )
    )
    now = datetime.now(UTC)
    user_id = uuid4()
    completed = CompletedIdempotencyResult(
        request_fingerprint=b"f" * 32,
        result_type="profile",
        result_payload={"user_id": user_id, "created_at": now},
        expires_at=utc_now() + timedelta(seconds=3600),
    )
    identity = IdempotencyKey(
        subject_id="actor", operation="update", key_digest=b"k" * 32
    )
    store = PostgresDurableIdempotencyStore(session)
    assert await store.try_add_completed(identity, completed) is inserted
    statement = session.execute.call_args.args[0]
    compiled = statement.compile(dialect=dialect())
    sql = str(compiled)
    assert "ON CONFLICT (subject_id, operation, key_digest) DO UPDATE" in sql
    assert "WHERE idempotency_records.expires_at <= excluded.created_at" in sql
    params = compiled.params
    assert params["expires_at"] == completed.expires_at
    assert params["request_fingerprint"] == b"f" * 32
    assert json.loads(json.dumps(params["result_payload"])) == {
        "user_id": str(user_id),
        "created_at": now.isoformat().replace("+00:00", "Z"),
    }


async def test_lookup_filters_expiry_in_database_and_refreshes_identity_map():
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
    )
    store = PostgresDurableIdempotencyStore(session)
    identity = IdempotencyKey(
        subject_id="actor", operation="update", key_digest=b"k" * 32
    )
    assert await store.get_completed(identity) is None
    statement = session.execute.call_args.args[0]
    assert "expires_at >" in str(statement.compile(dialect=dialect()))
    assert statement.get_execution_options()["populate_existing"] is True


async def test_completion_marker_is_written_without_payload_and_restored():
    completed = CompletedIdempotencyResult(
        result_type="completion",
        request_fingerprint=b"f" * 32,
        expires_at=utc_now() + timedelta(seconds=3600),
    )
    identity = IdempotencyKey(
        subject_id="user:1", operation="change", key_digest=b"k" * 32
    )
    row = SimpleNamespace(**completed.model_dump())
    session = SimpleNamespace(execute=AsyncMock())
    session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: uuid4())
    store = PostgresDurableIdempotencyStore(session)
    assert await store.try_add_completed(identity, completed)
    params = session.execute.call_args.args[0].compile(dialect=dialect()).params
    assert params["result_type"] == "completion"
    assert params["result_payload"] is None
    assert params["resource_id"] is None
    session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: row)
    assert await store.get_completed(identity) == completed

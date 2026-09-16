import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ValidationError

from app.application.exceptions.idempotency import StoredReplayUnavailableError
from app.application.idempotency.codec import PydanticResultCodec
from app.application.idempotency.models import StoredResult


class Response(BaseModel):
    user_id: UUID
    created_at: datetime
    amount: Decimal


@pytest.mark.parametrize(
    "value", [{"value": 42}, {"_empty": True}, {}, [1, 2], 42, None]
)
def test_replay_preserves_payload_shape(value):
    codec = PydanticResultCodec(type(value))
    stored = StoredResult.model_validate_json(codec.encode(value).model_dump_json())
    assert codec.decode(stored) == value


def test_dto_payload_is_json_safe_and_round_trips():
    codec = PydanticResultCodec(Response)
    response = Response(
        user_id=uuid4(), created_at=datetime.now(UTC), amount=Decimal("12.50")
    )
    stored = codec.encode(response)
    payload = json.loads(json.dumps(stored.result_payload))
    assert (
        codec.decode(stored.model_copy(update={"result_payload": payload})) == response
    )


def test_version_mismatch_is_an_application_error():
    codec = PydanticResultCodec(int, schema_version=2)
    with pytest.raises(StoredReplayUnavailableError):
        codec.decode(codec.encode(42).model_copy(update={"result_version": 1}))


def test_malformed_replay_is_an_application_error():
    stored = StoredResult(result_type="snapshot", result_payload={"value": "bad"})
    with pytest.raises(StoredReplayUnavailableError):
        PydanticResultCodec(int).decode(stored)


def test_invalid_handler_result_rejected_during_encode():
    with pytest.raises(ValidationError):
        PydanticResultCodec(int).encode("42")


def test_nullable_dto_round_trip():
    codec = PydanticResultCodec(Response | None)
    response = Response(
        user_id=uuid4(), created_at=datetime.now(UTC), amount=Decimal("1")
    )
    assert codec.decode(codec.encode(response)) == response
    assert codec.decode(codec.encode(None)) is None

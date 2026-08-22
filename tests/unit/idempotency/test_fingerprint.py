import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

import pytest
from pydantic import BaseModel

from app.application.idempotency.fingerprint import (
    compute_key_digest,
    compute_request_fingerprint,
)


class StatusEnum(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class SamplePayload(BaseModel):
    name: str
    amount: Decimal
    tags: list[str]
    created_at: datetime
    status: StatusEnum


def test_key_digest():
    digest = compute_key_digest("idemp-key-123")
    assert len(digest) == 32
    assert isinstance(digest, bytes)

    with pytest.raises(ValueError, match="Ключ идемпотентности не может быть пустым"):
        compute_key_digest("")


def test_request_fingerprint_deterministic():
    now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)
    payload1 = SamplePayload(
        name="Alex",
        amount=Decimal("100.50"),
        tags=["a", "b"],
        created_at=now,
        status=StatusEnum.ACTIVE,
    )
    payload2 = {
        "name": "Alex",
        "amount": Decimal("100.50"),
        "tags": ["a", "b"],
        "created_at": now,
        "status": StatusEnum.ACTIVE,
    }

    fp1 = compute_request_fingerprint(payload1)
    fp2 = compute_request_fingerprint(payload2)

    assert len(fp1) == 32
    assert fp1 == fp2


def test_request_fingerprint_unordered_paths():
    fp1 = compute_request_fingerprint(
        {"items": [{"id": 1}, {"id": 2}]},
        unordered_paths={("items",)},
    )
    fp2 = compute_request_fingerprint(
        {"items": [{"id": 2}, {"id": 1}]},
        unordered_paths={("items",)},
    )
    assert fp1 == fp2


def test_fingerprint_rejects_naive_datetime():
    naive = datetime(2026, 8, 22, 12, 0, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        compute_request_fingerprint({"time": naive})


def test_fingerprint_handles_uuid_date_and_set():
    u = uuid.uuid4()
    d = date(2026, 8, 22)
    s = {"x", "y"}
    fp = compute_request_fingerprint({"id": u, "date": d, "options": s})
    assert len(fp) == 32

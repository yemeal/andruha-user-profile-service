from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.idempotency.models import (
    CompletedIdempotencyResult,
    IdempotencyKey,
)
from app.domain.clock import utc_now
from app.infrastructure.idempotency.postgres.models import IdempotencyRecordORM


class PostgresDurableIdempotencyStore:
    """Реализация порта DurableIdempotencyStore для PostgreSQL."""

    def __init__(self, session: AsyncSession, *, retention_seconds: int) -> None:
        if retention_seconds <= 0:
            raise ValueError(
                "Параметр retention_seconds должен быть положительным числом"
            )
        self._session = session
        self._retention_seconds = retention_seconds

    async def get_completed(
        self, identity: IdempotencyKey
    ) -> CompletedIdempotencyResult | None:
        result = await self._session.execute(
            select(IdempotencyRecordORM).where(
                IdempotencyRecordORM.subject_id == identity.subject_id,
                IdempotencyRecordORM.operation == identity.operation,
                IdempotencyRecordORM.key_digest == identity.key_digest,
            )
        )
        row = result.scalar_one_or_none()
        if row is None or row.expires_at <= utc_now():
            return None
        return CompletedIdempotencyResult(
            request_fingerprint=row.request_fingerprint,
            result_type=row.result_type,
            result_payload=row.result_payload,
            result_version=row.result_version,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            resource_version=row.resource_version,
        )

    async def try_add_completed(
        self, identity: IdempotencyKey, completed: CompletedIdempotencyResult
    ) -> bool:
        now = utc_now()
        statement = (
            pg_insert(IdempotencyRecordORM)
            .values(
                subject_id=identity.subject_id,
                operation=identity.operation,
                key_digest=identity.key_digest,
                request_fingerprint=completed.request_fingerprint,
                fingerprint_version=1,
                result_type=completed.result_type,
                result_payload=completed.result_payload,
                result_version=completed.result_version,
                resource_type=completed.resource_type,
                resource_id=str(completed.resource_id)
                if completed.resource_id is not None
                else None,
                resource_version=completed.resource_version,
                created_at=now,
                completed_at=now,
                expires_at=now + timedelta(seconds=self._retention_seconds),
            )
            .on_conflict_do_nothing(
                index_elements=["subject_id", "operation", "key_digest"]
            )
            .returning(IdempotencyRecordORM.id)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none() is not None

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.exceptions.idempotency import IdempotencyUnavailableError
from app.application.idempotency.models import (
    CompletedIdempotencyResult,
    IdempotencyKey,
)
from app.domain.clock import utc_now
from app.infrastructure.idempotency.postgres.models import IdempotencyRecordORM


class PostgresDurableIdempotencyStore:
    """Хранит snapshot или отметку выполнения с expiry; не выбирает policy и не коммитит."""

    def __init__(
        self, session: AsyncSession, *, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._session = session
        self._clock = clock

    async def get_completed(
        self, identity: IdempotencyKey
    ) -> CompletedIdempotencyResult | None:
        result = await self._session.execute(
            select(IdempotencyRecordORM)
            .where(
                IdempotencyRecordORM.subject_id == identity.subject_id,
                IdempotencyRecordORM.operation == identity.operation,
                IdempotencyRecordORM.key_digest == identity.key_digest,
                IdempotencyRecordORM.expires_at > self._clock(),
            )
            .execution_options(populate_existing=True)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return CompletedIdempotencyResult(
            request_fingerprint=row.request_fingerprint,
            expires_at=row.expires_at,
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
        now = self._clock()
        if completed.expires_at <= now:
            raise IdempotencyUnavailableError(
                "Result expired before durable persistence"
            )
        payload = completed.model_dump(mode="json", exclude={"request_fingerprint"})
        statement = pg_insert(IdempotencyRecordORM).values(
            subject_id=identity.subject_id,
            operation=identity.operation,
            key_digest=identity.key_digest,
            request_fingerprint=completed.request_fingerprint,
            fingerprint_version=1,
            result_type=completed.result_type,
            result_payload=payload["result_payload"],
            result_version=completed.result_version,
            resource_type=completed.resource_type,
            resource_id=completed.resource_id,
            resource_version=completed.resource_version,
            created_at=now,
            completed_at=now,
            expires_at=completed.expires_at,
        )
        replacement = (
            "request_fingerprint",
            "fingerprint_version",
            "result_type",
            "result_payload",
            "result_version",
            "resource_type",
            "resource_id",
            "resource_version",
            "created_at",
            "completed_at",
            "expires_at",
        )
        statement = statement.on_conflict_do_update(
            index_elements=["subject_id", "operation", "key_digest"],
            set_={name: getattr(statement.excluded, name) for name in replacement},
            where=IdempotencyRecordORM.expires_at <= statement.excluded.created_at,
        ).returning(IdempotencyRecordORM.id)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none() is not None

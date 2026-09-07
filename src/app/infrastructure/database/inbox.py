from datetime import datetime
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models.inbox import ProcessedEventORM


class PostgresEventDeduplication:
    """Consumer-scoped durable fence; shares the business transaction, no TTL."""

    def __init__(self, session: AsyncSession, *, consumer: str) -> None:
        if not consumer.strip() or len(consumer) > 200:
            raise ValueError("consumer must contain 1..200 non-blank characters")
        self._session = session
        self._consumer = consumer

    async def mark_processed_if_absent(
        self, event_id: UUID, processed_at: datetime
    ) -> bool:
        if not self._session.in_transaction():
            raise RuntimeError("Inbox requires the business transaction/UoW")
        result = await self._session.scalar(
            insert(ProcessedEventORM)
            .values(
                consumer=self._consumer, event_id=event_id, processed_at=processed_at
            )
            .on_conflict_do_nothing()
            .returning(ProcessedEventORM.event_id)
        )
        return result is not None

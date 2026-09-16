from collections.abc import Sequence
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession


class BasePostgresReader[EntityT: BaseModel]:
    """Базовый PostgreSQL ридер (Read Side / Projections) с автоопределением PK."""

    def __init__(
        self,
        session: AsyncSession,
        table: Table,
        aggregate: type[EntityT],
    ) -> None:
        self._session = session
        self._table = table
        self._aggregate = aggregate
        self._pk_column = next(iter(table.primary_key.columns))

    async def get_by_id(self, entity_id: UUID) -> EntityT | None:
        row = (
            (
                await self._session.execute(
                    select(self._table).where(self._pk_column == entity_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        return self._aggregate.model_validate(dict(row)) if row is not None else None

    async def exists(self, entity_id: UUID) -> bool:
        return bool(
            await self._session.scalar(
                select(select(self._table).where(self._pk_column == entity_id).exists())
            )
        )

    async def get_batch(self, entity_ids: Sequence[UUID]) -> list[EntityT]:
        if not entity_ids:
            return []
        rows = (
            await self._session.execute(
                select(self._table).where(self._pk_column.in_(entity_ids))
            )
        ).mappings()
        return [self._aggregate.model_validate(dict(row)) for row in rows]

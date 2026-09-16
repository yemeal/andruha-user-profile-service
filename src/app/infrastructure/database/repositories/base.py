from uuid import UUID

from sqlalchemy import Table, delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.base import Entity
from app.infrastructure.exceptions.database import TransactionRequiredError


class BasePostgresRepository[EntityT: Entity]:
    """Base repository with optimistic concurrency control, generic PK and transaction enforcement."""

    missing_error: type[Exception]
    conflict_error: type[Exception]

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

    def _require_transaction(self) -> None:
        if not self._session.in_transaction():
            raise TransactionRequiredError()

    async def get_by_id(self, entity_id: UUID) -> EntityT | None:
        self._require_transaction()
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
        self._require_transaction()
        return bool(
            await self._session.scalar(
                select(select(self._table).where(self._pk_column == entity_id).exists())
            )
        )

    async def create(self, entity: EntityT) -> EntityT:
        self._require_transaction()
        values = entity.model_dump(exclude={"id"})
        values[self._pk_column.name] = entity.id
        row = (
            (
                await self._session.execute(
                    insert(self._table).values(**values).returning(self._table)
                )
            )
            .mappings()
            .one()
        )
        return self._aggregate.model_validate(dict(row))

    async def update(
        self, entity: EntityT, *, expected_version: int | None = None
    ) -> EntityT:
        self._require_transaction()
        values = entity.model_dump(exclude={"id", "created_at"})
        statement = update(self._table).where(self._pk_column == entity.id)
        if expected_version is not None:
            statement = statement.where(self._table.c.version == expected_version)
        row = (
            (
                await self._session.execute(
                    statement.values(**values).returning(self._table)
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            if not await self.exists(entity.id):
                raise self.missing_error()
            raise self.conflict_error()
        return self._aggregate.model_validate(dict(row))

    async def delete(self, entity_id: UUID) -> bool:
        self._require_transaction()
        deleted = await self._session.scalar(
            delete(self._table)
            .where(self._pk_column == entity_id)
            .returning(self._pk_column)
        )
        return deleted is not None

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import Table
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregates.settings import UserSettings
from app.domain.exceptions.user_settings import (
    SettingsVersionMismatchError,
    UserSettingsNotFoundError,
)
from app.infrastructure.database.models.settings import SettingsORM
from app.infrastructure.database.repositories.base import BasePostgresRepository


class PostgresSettingsRepository(BasePostgresRepository[UserSettings]):
    missing_error = UserSettingsNotFoundError
    conflict_error = SettingsVersionMismatchError

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(
            session,
            cast(Table, SettingsORM.__table__),
            UserSettings,
        )

    async def create_default_if_absent(
        self, user_id: UUID, now: datetime
    ) -> UserSettings:
        self._require_transaction()
        default_entity = UserSettings.create_default(user_id, now)
        values = default_entity.model_dump(exclude={"id"})
        values[self._pk_column.name] = default_entity.id
        row = (
            (
                await self._session.execute(
                    insert(self._table)
                    .values(**values)
                    .on_conflict_do_nothing(index_elements=[self._pk_column])
                    .returning(self._table)
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is not None:
            return self._aggregate.model_validate(dict(row))
        # A new READ COMMITTED statement sees the competing committed INSERT.
        existing = await self.get_by_id(user_id)
        if existing is None:
            # Concurrent deletion must not silently report a successful provision.
            raise self.missing_error()
        return existing

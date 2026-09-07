"""PostgreSQL repositories share the caller's transaction and never commit."""

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Table, delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregates.profiles import UserProfile
from app.domain.aggregates.settings import UserSettings
from app.domain.exceptions.user_profile import (
    ProfileVersionMismatchError,
    UsernameAlreadyTakenError,
    UserProfileNotFoundError,
)
from app.domain.exceptions.user_settings import (
    SettingsVersionMismatchError,
    UserSettingsNotFoundError,
)
from app.infrastructure.database.models.profiles import ProfileORM
from app.infrastructure.database.models.settings import SettingsORM


def _constraint_name(error: IntegrityError) -> str | None:
    original = error.orig
    return getattr(original, "constraint_name", None) or getattr(
        getattr(original, "__cause__", None), "constraint_name", None
    )


class _Repository[AggregateT: (UserProfile, UserSettings)]:
    def __init__(
        self,
        session: AsyncSession,
        table: Table,
        aggregate: type[AggregateT],
        missing: type[Exception],
        conflict: type[Exception],
    ) -> None:
        self._session = session
        self._table = table
        self._aggregate = aggregate
        self._missing = missing
        self._conflict = conflict

    def _require_transaction(self) -> None:
        if not self._session.in_transaction():
            raise RuntimeError("Repository requires an explicit transaction/UoW")

    def _values(self, entity: AggregateT) -> dict[str, Any]:
        # Validate even model_construct/model_copy input before sending SQL.
        validated = self._aggregate.model_validate(entity.model_dump())
        values = validated.model_dump()
        values["user_id"] = values.pop("id")
        return values

    async def get_by_id(self, entity_id: UUID) -> AggregateT | None:
        self._require_transaction()
        row = (
            (
                await self._session.execute(
                    select(self._table).where(self._table.c.user_id == entity_id)
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
                select(
                    select(self._table)
                    .where(self._table.c.user_id == entity_id)
                    .exists()
                )
            )
        )

    async def create(self, entity: AggregateT) -> AggregateT:
        self._require_transaction()
        try:
            row = (
                (
                    await self._session.execute(
                        insert(self._table)
                        .values(**self._values(entity))
                        .returning(self._table)
                    )
                )
                .mappings()
                .one()
            )
        except IntegrityError as error:
            if _constraint_name(error) == "profiles_username_key":
                raise UsernameAlreadyTakenError() from error
            raise
        return self._aggregate.model_validate(dict(row))

    async def create_default_if_absent(
        self, user_id: UUID, now: datetime
    ) -> AggregateT:
        self._require_transaction()
        values = self._values(self._aggregate.create_default(user_id, now))
        row = (
            (
                await self._session.execute(
                    insert(self._table)
                    .values(**values)
                    .on_conflict_do_nothing(index_elements=[self._table.c.user_id])
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
            raise self._missing()
        return existing

    async def update(
        self, entity: AggregateT, *, expected_version: int | None = None
    ) -> AggregateT:
        self._require_transaction()
        values = self._values(entity)
        values.pop("user_id")
        # Identity and creation time are immutable even for reconstructed input.
        values.pop("created_at")
        statement = update(self._table).where(self._table.c.user_id == entity.id)
        if expected_version is not None:
            statement = statement.where(self._table.c.version == expected_version)
        try:
            row = (
                (
                    await self._session.execute(
                        statement.values(**values).returning(self._table)
                    )
                )
                .mappings()
                .one_or_none()
            )
        except IntegrityError as error:
            if _constraint_name(error) == "profiles_username_key":
                raise UsernameAlreadyTakenError() from error
            raise
        if row is None:
            if not await self.exists(entity.id):
                raise self._missing()
            raise self._conflict()
        return self._aggregate.model_validate(dict(row))

    async def delete(self, entity_id: UUID) -> bool:
        self._require_transaction()
        deleted = await self._session.scalar(
            delete(self._table)
            .where(self._table.c.user_id == entity_id)
            .returning(self._table.c.user_id)
        )
        return deleted is not None


class PostgresProfileRepository(_Repository[UserProfile]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(
            session,
            cast(Table, ProfileORM.__table__),
            UserProfile,
            UserProfileNotFoundError,
            ProfileVersionMismatchError,
        )


class PostgresSettingsRepository(_Repository[UserSettings]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(
            session,
            cast(Table, SettingsORM.__table__),
            UserSettings,
            UserSettingsNotFoundError,
            SettingsVersionMismatchError,
        )

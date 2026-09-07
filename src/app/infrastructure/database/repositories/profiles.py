from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import Table
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregates.profiles import UserProfile
from app.domain.exceptions.user_profile import (
    ProfileVersionMismatchError,
    UsernameAlreadyTakenError,
    UserProfileNotFoundError,
)
from app.infrastructure.database.models.profiles import ProfileORM
from app.infrastructure.database.repositories.base import BasePostgresRepository


def _constraint_name(error: IntegrityError) -> str | None:
    original = error.orig
    return getattr(original, "constraint_name", None) or getattr(
        getattr(original, "__cause__", None), "constraint_name", None
    )


class PostgresProfileRepository(BasePostgresRepository[UserProfile]):
    missing_error = UserProfileNotFoundError
    conflict_error = ProfileVersionMismatchError

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(
            session,
            cast(Table, ProfileORM.__table__),
            UserProfile,
        )

    async def create(self, entity: UserProfile) -> UserProfile:
        try:
            return await super().create(entity)
        except IntegrityError as error:
            if _constraint_name(error) == "profiles_username_key":
                raise UsernameAlreadyTakenError() from error
            raise

    async def update(
        self, entity: UserProfile, *, expected_version: int | None = None
    ) -> UserProfile:
        try:
            return await super().update(entity, expected_version=expected_version)
        except IntegrityError as error:
            if _constraint_name(error) == "profiles_username_key":
                raise UsernameAlreadyTakenError() from error
            raise

    async def create_default_if_absent(
        self, user_id: UUID, now: datetime
    ) -> UserProfile:
        self._require_transaction()
        default_entity = UserProfile.create_default(user_id, now)
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

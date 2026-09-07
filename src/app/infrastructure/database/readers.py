"""Read-only port surfaces. Returned aggregates are detached validated values."""

from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregates.profiles import UserProfile
from app.domain.aggregates.settings import UserSettings
from app.domain.value_objects.username import Username
from app.infrastructure.database.models.profiles import ProfileORM
from app.infrastructure.database.repositories import (
    PostgresProfileRepository,
    PostgresSettingsRepository,
)


class PostgresProfileReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = PostgresProfileRepository(session)

    async def get_by_id(self, user_id: UUID) -> UserProfile | None:
        return await self._repository.get_by_id(user_id)

    async def exists(self, user_id: UUID) -> bool:
        return await self._repository.exists(user_id)

    async def get_by_username(self, username: Username | str) -> UserProfile | None:
        if not self._session.in_transaction():
            raise RuntimeError("Reader requires an explicit transaction")
        table = cast(Table, ProfileORM.__table__)
        row = (
            (
                await self._session.execute(
                    select(table).where(table.c.username == Username(username))
                )
            )
            .mappings()
            .one_or_none()
        )
        return UserProfile.model_validate(dict(row)) if row is not None else None

    async def get_batch(self, user_ids: Sequence[UUID]) -> list[UserProfile]:
        if not self._session.in_transaction():
            raise RuntimeError("Reader requires an explicit transaction")
        if not user_ids:
            return []
        table = cast(Table, ProfileORM.__table__)
        rows = (
            await self._session.execute(
                select(table).where(table.c.user_id.in_(user_ids))
            )
        ).mappings()
        return [UserProfile.model_validate(dict(row)) for row in rows]


class PostgresSettingsReader:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = PostgresSettingsRepository(session)

    async def get_by_id(self, user_id: UUID) -> UserSettings | None:
        return await self._repository.get_by_id(user_id)

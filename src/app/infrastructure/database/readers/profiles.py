from typing import cast

from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregates.profiles import UserProfile
from app.domain.value_objects.username import Username
from app.infrastructure.database.models.profiles import ProfileORM
from app.infrastructure.database.readers.base import BasePostgresReader


class PostgresProfileReader(BasePostgresReader[UserProfile]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(
            session=session,
            table=cast(Table, ProfileORM.__table__),
            aggregate=UserProfile,
        )

    async def get_by_username(self, username: Username | str) -> UserProfile | None:
        row = (
            (
                await self._session.execute(
                    select(self._table).where(
                        self._table.c.username == Username(username)
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return self._aggregate.model_validate(dict(row)) if row is not None else None

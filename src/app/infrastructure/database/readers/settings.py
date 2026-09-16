from typing import cast

from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregates.settings import UserSettings
from app.infrastructure.database.models.settings import SettingsORM
from app.infrastructure.database.readers.base import BasePostgresReader


class PostgresSettingsReader(BasePostgresReader[UserSettings]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(
            session=session,
            table=cast(Table, SettingsORM.__table__),
            aggregate=UserSettings,
        )

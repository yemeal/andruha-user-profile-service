from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infrastructure.database.config import DatabaseSettings
from app.infrastructure.database.readers import (
    PostgresProfileReader,
    PostgresSettingsReader,
)
from app.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork


@dataclass(frozen=True, slots=True)
class ProfileReaders:
    profiles: PostgresProfileReader
    settings: PostgresSettingsReader


class ProfileDatabase:
    """One engine per process; one session per command dispatch or read scope."""

    def __init__(self, settings: DatabaseSettings) -> None:
        self.engine = create_async_engine(
            settings.database_url.get_secret_value(),
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout,
            pool_pre_ping=True,
            isolation_level="READ COMMITTED",
            connect_args={"command_timeout": settings.database_command_timeout},
            hide_parameters=True,
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def readers(self) -> AsyncGenerator[ProfileReaders]:
        async with self.sessions() as session, SqlAlchemyUnitOfWork(session):
            await session.execute(text("SET TRANSACTION READ ONLY"))
            yield ProfileReaders(
                PostgresProfileReader(session), PostgresSettingsReader(session)
            )

    async def check_ready(self) -> None:
        async with self.sessions() as session, SqlAlchemyUnitOfWork(session):
            await session.execute(text("SELECT 1"))

    async def close(self) -> None:
        await self.engine.dispose()

from collections.abc import AsyncIterator

import dishka
from dishka import Provider, Scope
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.application.ports.persistence.unit_of_work import AsyncUOWProtocol
from app.core.settings import PostgresSettings
from app.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork


class DatabaseAppProvider(Provider):
    scope = Scope.APP

    @dishka.provide
    async def engine(self, settings: PostgresSettings) -> AsyncIterator[AsyncEngine]:
        engine = create_async_engine(
            settings.database_url.get_secret_value(),
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout,
            pool_pre_ping=True,
            isolation_level="READ COMMITTED",
            connect_args={"command_timeout": settings.database_command_timeout},
            hide_parameters=True,
        )
        try:
            yield engine
        finally:
            await engine.dispose()

    @dishka.provide
    def sessionmaker(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(engine, expire_on_commit=False)


class DatabaseRequestProvider(Provider):
    scope = Scope.REQUEST

    @dishka.provide
    async def session(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    @dishka.provide
    def uow(self, session: AsyncSession) -> AsyncUOWProtocol:
        return SqlAlchemyUnitOfWork(session)

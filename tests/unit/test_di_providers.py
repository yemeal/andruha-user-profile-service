from __future__ import annotations

import pytest
from dishka import AsyncContainer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.dispatching.bus import CommandBus, CommandBusProtocol
from app.application.dispatching.registry import CommandHandlerRegistry
from app.application.idempotency.coordinator import IdempotencyCoordinator
from app.application.idempotency.transactional_execution import (
    TransactionalIdempotencyExecution,
)
from app.application.ports.idempotency.durable_execution import DurableExecution
from app.application.ports.idempotency.durable_store import DurableIdempotencyStore
from app.application.ports.idempotency.hot_store import HotIdempotencyStore
from app.application.ports.observability.idempotency_metrics import IdempotencyMetrics
from app.application.ports.persistence.readers.profiles import (
    ProfileReaderProtocol,
)
from app.application.ports.persistence.readers.settings import (
    SettingsReaderProtocol,
)
from app.application.ports.persistence.repositories.profiles import (
    ProfileRepositoryProtocol,
)
from app.application.ports.persistence.repositories.settings import (
    SettingsRepositoryProtocol,
)
from app.application.ports.persistence.unit_of_work import AsyncUOWProtocol
from app.application.queries.profiles.check_exists.handler import (
    CheckProfileExistsHandler,
)
from app.application.queries.profiles.get_batch.handler import (
    GetBatchProfilesHandler,
)
from app.application.queries.profiles.get_my.handler import GetMyProfileHandler
from app.application.queries.profiles.get_public.handler import (
    GetPublicProfileHandler,
)
from app.application.queries.profiles.search_by_username.handler import (
    SearchByUsernameHandler,
)
from app.application.queries.settings.get_my.handler import GetMySettingsHandler
from app.core.settings import (
    AppSettings,
    IdempotencySettings,
    PostgresSettings,
    RedisSettings,
    Settings,
)
from app.entrypoints.http.main import create_app
from app.infrastructure.database.readers import (
    PostgresProfileReader,
    PostgresSettingsReader,
)
from app.infrastructure.database.repositories import (
    PostgresProfileRepository,
    PostgresSettingsRepository,
)
from app.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.di import (
    ProfileDependencies,
    create_container,
)
from app.infrastructure.idempotency.observability.idempotency_metrics import (
    PrometheusIdempotencyMetrics,
)
from app.infrastructure.idempotency.postgres.durable_store import (
    PostgresDurableIdempotencyStore,
)
from app.infrastructure.idempotency.redis.circuit_breaking_hot_store import (
    CircuitBreakingHotStore,
)
from app.infrastructure.resilience.circuit_breaker import IdempotencyCircuitBreaker


def test_di_exports_all_scoped_providers() -> None:
    from app.infrastructure import di

    assert hasattr(di, "SettingsProvider")
    assert hasattr(di, "DatabaseAppProvider")
    assert hasattr(di, "DatabaseRequestProvider")
    assert hasattr(di, "IdempotencyAppProvider")
    assert hasattr(di, "IdempotencyRequestProvider")
    assert hasattr(di, "RepositoriesProvider")
    assert hasattr(di, "CommandBusProvider")
    assert hasattr(di, "CommandsProvider")
    assert hasattr(di, "QueriesProvider")
    assert hasattr(di, "create_container")
    assert hasattr(di, "build_command_bus")
    assert hasattr(di, "build_profile_command_bus")
    assert hasattr(di, "build_command_registry")
    assert hasattr(di, "build_profile_registry")
    assert hasattr(di, "CommandDependencies")
    assert hasattr(di, "ProfileDependencies")


@pytest.mark.asyncio
async def test_container_resolves_all_settings() -> None:
    container: AsyncContainer = create_container()
    try:
        settings = await container.get(Settings)
        assert isinstance(settings, Settings)
        assert await container.get(AppSettings) == settings.app
        assert await container.get(PostgresSettings) == settings.postgres
        assert await container.get(RedisSettings) == settings.redis
        assert await container.get(IdempotencySettings) == settings.idempotency
    finally:
        await container.close()


@pytest.mark.asyncio
async def test_container_resolves_app_scope_infrastructure() -> None:
    container: AsyncContainer = create_container()
    try:
        # Database Engine & Sessionmaker
        engine = await container.get(AsyncEngine)
        assert isinstance(engine, AsyncEngine)
        sm = await container.get(async_sessionmaker[AsyncSession])
        assert isinstance(sm, async_sessionmaker)

        # Idempotency & Hot store
        metrics = await container.get(IdempotencyMetrics)
        assert isinstance(metrics, PrometheusIdempotencyMetrics)
        redis_client = await container.get(Redis)
        assert isinstance(redis_client, Redis)
        cb = await container.get(IdempotencyCircuitBreaker)
        assert isinstance(cb, IdempotencyCircuitBreaker)
        hot = await container.get(HotIdempotencyStore)
        assert isinstance(hot, CircuitBreakingHotStore)

        # Command bus & registry
        registry = await container.get(CommandHandlerRegistry[ProfileDependencies])
        assert isinstance(registry, CommandHandlerRegistry)
        bus = await container.get(CommandBusProtocol)
        assert isinstance(bus, CommandBus)
    finally:
        await container.close()


@pytest.mark.asyncio
async def test_container_resolves_request_scope_dependencies() -> None:
    container: AsyncContainer = create_container()
    try:
        async with container() as request_container:
            # Session & UOW
            session = await request_container.get(AsyncSession)
            assert isinstance(session, AsyncSession)
            uow = await request_container.get(AsyncUOWProtocol)
            assert isinstance(uow, SqlAlchemyUnitOfWork)

            # Repositories & Readers
            profile_repo = await request_container.get(ProfileRepositoryProtocol)
            assert isinstance(profile_repo, PostgresProfileRepository)
            settings_repo = await request_container.get(SettingsRepositoryProtocol)
            assert isinstance(settings_repo, PostgresSettingsRepository)

            profile_reader = await request_container.get(ProfileReaderProtocol)
            assert isinstance(profile_reader, PostgresProfileReader)
            settings_reader = await request_container.get(SettingsReaderProtocol)
            assert isinstance(settings_reader, PostgresSettingsReader)

            # Durable store & coordinator
            durable_store = await request_container.get(DurableIdempotencyStore)
            assert isinstance(durable_store, PostgresDurableIdempotencyStore)
            durable_exec = await request_container.get(DurableExecution)
            assert isinstance(durable_exec, TransactionalIdempotencyExecution)
            coord = await request_container.get(IdempotencyCoordinator)
            assert isinstance(coord, IdempotencyCoordinator)

            # Query handlers
            assert isinstance(
                await request_container.get(GetMyProfileHandler),
                GetMyProfileHandler,
            )
            assert isinstance(
                await request_container.get(GetPublicProfileHandler),
                GetPublicProfileHandler,
            )
            assert isinstance(
                await request_container.get(SearchByUsernameHandler),
                SearchByUsernameHandler,
            )
            assert isinstance(
                await request_container.get(GetBatchProfilesHandler),
                GetBatchProfilesHandler,
            )
            assert isinstance(
                await request_container.get(CheckProfileExistsHandler),
                CheckProfileExistsHandler,
            )
            assert isinstance(
                await request_container.get(GetMySettingsHandler),
                GetMySettingsHandler,
            )
    finally:
        await container.close()


def test_fastapi_dishka_integration() -> None:
    app = create_app()
    assert hasattr(app.state, "dishka_container")

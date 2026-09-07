from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.dispatching.bus import CommandBus
from app.application.dispatching.execution import CommandExecution
from app.application.dispatching.registry import CommandHandlerRegistry
from app.application.idempotency.coordinator import IdempotencyCoordinator
from app.application.idempotency.middleware import IdempotencyMiddleware
from app.application.idempotency.transactional_execution import (
    TransactionalIdempotencyExecution,
)
from app.application.ports.idempotency.hot_store import HotIdempotencyStore
from app.application.ports.observability.idempotency_metrics import IdempotencyMetrics
from app.domain.clock import utc_now
from app.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.idempotency.postgres.durable_store import (
    PostgresDurableIdempotencyStore,
)


def build_postgres_command_bus[DependenciesT](
    registry: CommandHandlerRegistry[DependenciesT],
    *,
    sessions: async_sessionmaker[AsyncSession],
    dependencies_factory: Callable[[AsyncSession], DependenciesT],
    hot_store: HotIdempotencyStore,
    metrics: IdempotencyMetrics | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> CommandBus[DependenciesT]:
    """Создаёт bus; session, repositories, UoW и executor живут один dispatch.

    dependencies_factory собирает application-зависимости handler из переданной
    session. Она не должна открывать другую session или выполнять SQL.
    Hot adapter и его circuit breaker можно разделять между dispatch.
    """

    @asynccontextmanager
    async def scope() -> AsyncGenerator[CommandExecution[DependenciesT]]:
        async with sessions() as session:
            uow = SqlAlchemyUnitOfWork(session)
            dependencies = dependencies_factory(session)
            durable_store = PostgresDurableIdempotencyStore(session, clock=clock)
            durable = TransactionalIdempotencyExecution(durable_store, uow, clock=clock)
            coordinator = IdempotencyCoordinator(
                hot_store, durable, metrics=metrics, clock=clock
            )
            yield CommandExecution(
                dependencies, uow, IdempotencyMiddleware(coordinator)
            )

    return CommandBus(registry, scope)

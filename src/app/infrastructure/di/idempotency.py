from collections.abc import AsyncIterator

import dishka
from dishka import Provider, Scope
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.idempotency.coordinator import IdempotencyCoordinator
from app.application.idempotency.transactional_execution import (
    TransactionalIdempotencyExecution,
)
from app.application.ports.idempotency.durable_execution import (
    DurableExecution,
)
from app.application.ports.idempotency.durable_store import DurableIdempotencyStore
from app.application.ports.idempotency.hot_store import HotIdempotencyStore
from app.application.ports.observability.idempotency_metrics import IdempotencyMetrics
from app.application.ports.persistence.unit_of_work import AsyncUOWProtocol
from app.core.settings import IdempotencySettings, RedisSettings
from app.infrastructure.idempotency.observability.idempotency_metrics import (
    PrometheusIdempotencyMetrics,
)
from app.infrastructure.idempotency.postgres.durable_store import (
    PostgresDurableIdempotencyStore,
)
from app.infrastructure.idempotency.redis.circuit_breaking_hot_store import (
    CircuitBreakingHotStore,
)
from app.infrastructure.idempotency.redis.hot_store import RedisHotIdempotencyStore
from app.infrastructure.resilience.circuit_breaker import IdempotencyCircuitBreaker


class IdempotencyAppProvider(Provider):
    scope = Scope.APP

    @dishka.provide
    def metrics(self) -> IdempotencyMetrics:
        return PrometheusIdempotencyMetrics()

    @dishka.provide
    async def redis(self, settings: RedisSettings) -> AsyncIterator[Redis]:
        client = Redis.from_url(
            settings.url.get_secret_value(),
            decode_responses=False,
            max_connections=settings.max_connections,
            socket_timeout=settings.socket_timeout,
            socket_connect_timeout=settings.socket_connect_timeout,
            health_check_interval=settings.health_check_interval,
        )
        try:
            yield client
        finally:
            await client.aclose()

    @dishka.provide
    def circuit_breaker(
        self, settings: IdempotencySettings
    ) -> IdempotencyCircuitBreaker:
        return IdempotencyCircuitBreaker(
            settings.cb_failures,
            settings.cb_recovery_seconds,
            "user-profile-idempotency-redis",
        )

    @dishka.provide
    def hot_store(
        self,
        redis: Redis,
        circuit_breaker: IdempotencyCircuitBreaker,
        settings: RedisSettings,
    ) -> HotIdempotencyStore:
        inner = RedisHotIdempotencyStore(redis, key_namespace=settings.key_namespace)
        return CircuitBreakingHotStore(inner, circuit_breaker)


class IdempotencyRequestProvider(Provider):
    scope = Scope.REQUEST

    @dishka.provide
    def durable_store(self, session: AsyncSession) -> DurableIdempotencyStore:
        return PostgresDurableIdempotencyStore(session)

    @dishka.provide
    def durable_execution(
        self, store: DurableIdempotencyStore, uow: AsyncUOWProtocol
    ) -> DurableExecution:
        return TransactionalIdempotencyExecution(store, uow)

    @dishka.provide
    def coordinator(
        self,
        hot_store: HotIdempotencyStore,
        durable: DurableExecution,
        metrics: IdempotencyMetrics,
    ) -> IdempotencyCoordinator:
        return IdempotencyCoordinator(hot_store, durable, metrics=metrics)

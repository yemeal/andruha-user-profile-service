from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime

import dishka
from dishka import AsyncContainer, Provider, Scope
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.commands.profiles.create_default.command import (
    CreateDefaultProfileCommand,
)
from app.application.commands.profiles.create_default.handler import (
    CreateDefaultProfileHandler,
)
from app.application.commands.profiles.update.command import UpdateProfileCommand
from app.application.commands.profiles.update.handler import UpdateProfileHandler
from app.application.commands.profiles.update_avatar.command import UpdateAvatarCommand
from app.application.commands.profiles.update_avatar.handler import UpdateAvatarHandler
from app.application.commands.settings.reset.command import ResetSettingsCommand
from app.application.commands.settings.reset.handler import ResetSettingsHandler
from app.application.commands.settings.update.command import UpdateSettingsCommand
from app.application.commands.settings.update.handler import UpdateSettingsHandler
from app.application.dispatching.bus import CommandBus, CommandBusProtocol
from app.application.dispatching.execution import CommandExecution
from app.application.dispatching.registry import CommandHandlerRegistry
from app.application.dto import ProfileDTO, SettingsDTO
from app.application.idempotency.coordinator import IdempotencyCoordinator
from app.application.idempotency.middleware import IdempotencyMiddleware
from app.application.idempotency.policy import IdempotencyMode, IdempotencyPolicy
from app.application.idempotency.transactional_execution import (
    TransactionalIdempotencyExecution,
)
from app.application.ports.idempotency.hot_store import HotIdempotencyStore
from app.application.ports.observability.idempotency_metrics import IdempotencyMetrics
from app.application.ports.persistence.repositories.profiles import (
    ProfileRepositoryProtocol,
)
from app.application.ports.persistence.repositories.settings import (
    SettingsRepositoryProtocol,
)
from app.application.ports.persistence.unit_of_work import AsyncUOWProtocol
from app.core.settings import IdempotencySettings
from app.domain.clock import utc_now
from app.infrastructure.database.repositories import (
    PostgresProfileRepository,
    PostgresSettingsRepository,
)
from app.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.idempotency.postgres.durable_store import (
    PostgresDurableIdempotencyStore,
)


@dataclass(frozen=True, slots=True)
class CommandDependencies:
    profiles: ProfileRepositoryProtocol
    settings: SettingsRepositoryProtocol

    @classmethod
    def from_session(cls, session: AsyncSession) -> CommandDependencies:
        return cls(
            PostgresProfileRepository(session),
            PostgresSettingsRepository(session),
        )


ProfileDependencies = CommandDependencies


def build_command_registry(
    *,
    mutation_policy: IdempotencyPolicy | None = None,
    provisioning_policy: IdempotencyPolicy | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> CommandHandlerRegistry[CommandDependencies]:
    mut_policy = (
        mutation_policy
        if mutation_policy is not None
        else IdempotencyPolicy(
            mode=IdempotencyMode.HOT_DURABLE,
            lease_seconds=30,
            retention_seconds=86400,
        )
    )
    prov_policy = (
        provisioning_policy
        if provisioning_policy is not None
        else IdempotencyPolicy(
            mode=IdempotencyMode.HOT_DURABLE,
            lease_seconds=30,
            retention_seconds=86400,
        )
    )
    if prov_policy.mode is not IdempotencyMode.HOT_DURABLE:
        raise ValueError("provisioning requires HOT_DURABLE idempotency")

    registry = CommandHandlerRegistry[CommandDependencies]()
    registry.register(
        CreateDefaultProfileCommand,
        lambda deps: CreateDefaultProfileHandler(deps.profiles, deps.settings),
        result_type=type(None),
        operation="profile.create_default.v1",
        idempotency_policy=prov_policy,
    )
    registry.register(
        UpdateProfileCommand,
        lambda deps: UpdateProfileHandler(deps.profiles, clock),
        result_type=ProfileDTO,
        operation="profile.update.v1",
        idempotency_policy=mut_policy,
    )
    registry.register(
        UpdateAvatarCommand,
        lambda deps: UpdateAvatarHandler(deps.profiles, clock),
        result_type=ProfileDTO,
        operation="profile.update_avatar.v1",
        idempotency_policy=mut_policy,
    )
    registry.register(
        UpdateSettingsCommand,
        lambda deps: UpdateSettingsHandler(deps.settings, clock),
        result_type=SettingsDTO,
        operation="settings.update.v1",
        idempotency_policy=mut_policy,
    )
    registry.register(
        ResetSettingsCommand,
        lambda deps: ResetSettingsHandler(deps.settings, clock),
        result_type=SettingsDTO,
        operation="settings.reset.v1",
        idempotency_policy=mut_policy,
    )
    return registry


build_profile_registry = build_command_registry


class CommandsProvider(Provider):
    scope = Scope.APP

    @dishka.provide
    def registry(
        self, idempotency_settings: IdempotencySettings
    ) -> CommandHandlerRegistry[CommandDependencies]:
        policy = IdempotencyPolicy(
            mode=IdempotencyMode.HOT_DURABLE,
            lease_seconds=idempotency_settings.lease_seconds,
            retention_seconds=idempotency_settings.result_ttl_seconds,
        )
        return build_command_registry(
            mutation_policy=policy,
            provisioning_policy=policy,
        )

    @dishka.provide
    def command_bus(
        self,
        container: AsyncContainer,
        registry: CommandHandlerRegistry[CommandDependencies],
    ) -> CommandBusProtocol:
        @asynccontextmanager
        async def scope_factory() -> AsyncGenerator[
            CommandExecution[CommandDependencies]
        ]:
            async with container() as request_container:
                profiles_repo = await request_container.get(ProfileRepositoryProtocol)
                settings_repo = await request_container.get(SettingsRepositoryProtocol)
                uow = await request_container.get(AsyncUOWProtocol)
                coordinator = await request_container.get(IdempotencyCoordinator)
                deps = CommandDependencies(
                    profiles=profiles_repo, settings=settings_repo
                )
                yield CommandExecution(
                    deps,
                    uow,
                    IdempotencyMiddleware(coordinator),
                )

        return CommandBus(registry, scope_factory)


CommandBusProvider = CommandsProvider


def build_command_bus(
    sessions: async_sessionmaker[AsyncSession],
    *,
    hot_store: HotIdempotencyStore,
    mutation_policy: IdempotencyPolicy,
    provisioning_policy: IdempotencyPolicy,
    metrics: IdempotencyMetrics | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> CommandBus[CommandDependencies]:
    """Use existing durable execution for provisioning and caller policies for mutations.

    Registration callers supply event identity through CommandContext and dispatch
    with COMPLETION_ONLY. Repositories share the durable execution transaction.
    """
    registry = build_command_registry(
        mutation_policy=mutation_policy,
        provisioning_policy=provisioning_policy,
        clock=clock,
    )

    @asynccontextmanager
    async def scope() -> AsyncGenerator[CommandExecution[CommandDependencies]]:
        async with sessions() as session:
            uow = SqlAlchemyUnitOfWork(session)
            dependencies = CommandDependencies.from_session(session)
            durable_store = PostgresDurableIdempotencyStore(session, clock=clock)
            durable = TransactionalIdempotencyExecution(durable_store, uow, clock=clock)
            coordinator = IdempotencyCoordinator(
                hot_store, durable, metrics=metrics, clock=clock
            )
            yield CommandExecution(
                dependencies, uow, IdempotencyMiddleware(coordinator)
            )

    return CommandBus(registry, scope)


build_profile_command_bus = build_command_bus

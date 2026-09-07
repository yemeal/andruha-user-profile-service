from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

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
from app.application.dispatching.bus import CommandBus
from app.application.dispatching.registry import CommandHandlerRegistry
from app.application.dto import ProfileDTO, SettingsDTO
from app.application.idempotency.policy import IdempotencyMode, IdempotencyPolicy
from app.application.ports.idempotency.hot_store import HotIdempotencyStore
from app.application.ports.observability.idempotency_metrics import IdempotencyMetrics
from app.domain.clock import utc_now
from app.infrastructure.database.repositories import (
    PostgresProfileRepository,
    PostgresSettingsRepository,
)
from app.infrastructure.di.command_bus import build_postgres_command_bus


@dataclass(frozen=True, slots=True)
class ProfileDependencies:
    profiles: PostgresProfileRepository
    settings: PostgresSettingsRepository

    @classmethod
    def from_session(cls, session: AsyncSession) -> ProfileDependencies:
        return cls(
            PostgresProfileRepository(session),
            PostgresSettingsRepository(session),
        )


def build_profile_command_bus(
    sessions: async_sessionmaker[AsyncSession],
    *,
    hot_store: HotIdempotencyStore,
    mutation_policy: IdempotencyPolicy,
    provisioning_policy: IdempotencyPolicy,
    metrics: IdempotencyMetrics | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> CommandBus[ProfileDependencies]:
    """Use existing durable execution for provisioning and caller policies for mutations.

    Registration callers supply event identity through CommandContext and dispatch
    with COMPLETION_ONLY. Repositories share the durable execution transaction.
    """
    if provisioning_policy.mode is not IdempotencyMode.HOT_DURABLE:
        raise ValueError("provisioning requires HOT_DURABLE idempotency")
    registry = CommandHandlerRegistry[ProfileDependencies]()
    registry.register(
        CreateDefaultProfileCommand,
        lambda deps: CreateDefaultProfileHandler(deps.profiles, deps.settings),
        result_type=type(None),
        operation="profile.create_default.v1",
        idempotency_policy=provisioning_policy,
    )
    registry.register(
        UpdateProfileCommand,
        lambda deps: UpdateProfileHandler(deps.profiles, clock),
        result_type=ProfileDTO,
        operation="profile.update.v1",
        idempotency_policy=mutation_policy,
    )
    registry.register(
        UpdateAvatarCommand,
        lambda deps: UpdateAvatarHandler(deps.profiles, clock),
        result_type=ProfileDTO,
        operation="profile.update_avatar.v1",
        idempotency_policy=mutation_policy,
    )
    registry.register(
        UpdateSettingsCommand,
        lambda deps: UpdateSettingsHandler(deps.settings, clock),
        result_type=SettingsDTO,
        operation="settings.update.v1",
        idempotency_policy=mutation_policy,
    )
    registry.register(
        ResetSettingsCommand,
        lambda deps: ResetSettingsHandler(deps.settings, clock),
        result_type=SettingsDTO,
        operation="settings.reset.v1",
        idempotency_policy=mutation_policy,
    )
    return build_postgres_command_bus(
        registry,
        sessions=sessions,
        dependencies_factory=ProfileDependencies.from_session,
        hot_store=hot_store,
        metrics=metrics,
        clock=clock,
    )

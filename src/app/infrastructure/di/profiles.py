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
from app.application.idempotency.policy import IdempotencyPolicy
from app.application.idempotency.registration import RegistrationDeduplication
from app.application.ports.idempotency.hot_store import HotIdempotencyStore
from app.application.ports.observability.idempotency_metrics import IdempotencyMetrics
from app.domain.clock import utc_now
from app.infrastructure.database.inbox import PostgresEventDeduplication
from app.infrastructure.database.repositories import (
    PostgresProfileRepository,
    PostgresSettingsRepository,
)
from app.infrastructure.di.command_bus import build_postgres_command_bus


@dataclass(frozen=True, slots=True)
class ProfileDependencies:
    profiles: PostgresProfileRepository
    settings: PostgresSettingsRepository
    inbox: PostgresEventDeduplication

    @classmethod
    def from_session(cls, session: AsyncSession) -> ProfileDependencies:
        return cls(
            PostgresProfileRepository(session),
            PostgresSettingsRepository(session),
            PostgresEventDeduplication(session, consumer="profile.user_registered.v1"),
        )


def build_profile_command_bus(
    sessions: async_sessionmaker[AsyncSession],
    *,
    hot_store: HotIdempotencyStore,
    mutation_policy: IdempotencyPolicy,
    metrics: IdempotencyMetrics | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> CommandBus[ProfileDependencies]:
    """Provisioning is naturally idempotent; mutations use the explicit caller policy.

    Event commands persist their Inbox fence in the bus-owned UoW. A consumer
    must not wrap this command bus in a second transaction.
    """
    registry = CommandHandlerRegistry[ProfileDependencies]()
    registry.register(
        CreateDefaultProfileCommand,
        lambda deps: RegistrationDeduplication(
            CreateDefaultProfileHandler(deps.profiles, deps.settings), deps.inbox, clock
        ),
        result_type=type(None),
        operation="profile.create_default.v1",
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

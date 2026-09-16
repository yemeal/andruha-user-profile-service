from dishka import AsyncContainer, Provider, make_async_container

from app.infrastructure.di.commands import (
    CommandBusProvider,
    CommandDependencies,
    CommandsProvider,
    ProfileDependencies,
    build_command_bus,
    build_command_registry,
    build_profile_command_bus,
    build_profile_registry,
)
from app.infrastructure.di.database import (
    DatabaseAppProvider,
    DatabaseRequestProvider,
)
from app.infrastructure.di.idempotency import (
    IdempotencyAppProvider,
    IdempotencyRequestProvider,
)
from app.infrastructure.di.queries import QueriesProvider
from app.infrastructure.di.repositories import RepositoriesProvider
from app.infrastructure.di.settings import SettingsProvider


def create_container(*extra_providers: Provider) -> AsyncContainer:
    return make_async_container(
        SettingsProvider(),
        DatabaseAppProvider(),
        DatabaseRequestProvider(),
        IdempotencyAppProvider(),
        IdempotencyRequestProvider(),
        RepositoriesProvider(),
        CommandsProvider(),
        QueriesProvider(),
        *extra_providers,
    )


__all__ = [
    "CommandBusProvider",
    "CommandDependencies",
    "CommandsProvider",
    "DatabaseAppProvider",
    "DatabaseRequestProvider",
    "IdempotencyAppProvider",
    "IdempotencyRequestProvider",
    "ProfileDependencies",
    "QueriesProvider",
    "RepositoriesProvider",
    "SettingsProvider",
    "build_command_bus",
    "build_command_registry",
    "build_profile_command_bus",
    "build_profile_registry",
    "create_container",
]

import dishka
from dishka import Provider, Scope
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.infrastructure.database.readers import (
    PostgresProfileReader,
    PostgresSettingsReader,
)
from app.infrastructure.database.repositories import (
    PostgresProfileRepository,
    PostgresSettingsRepository,
)


class RepositoriesProvider(Provider):
    scope = Scope.REQUEST

    @dishka.provide
    def profile_repository(self, session: AsyncSession) -> ProfileRepositoryProtocol:
        return PostgresProfileRepository(session)

    @dishka.provide
    def settings_repository(self, session: AsyncSession) -> SettingsRepositoryProtocol:
        return PostgresSettingsRepository(session)

    @dishka.provide
    def profile_reader(self, session: AsyncSession) -> ProfileReaderProtocol:
        return PostgresProfileReader(session)

    @dishka.provide
    def settings_reader(self, session: AsyncSession) -> SettingsReaderProtocol:
        return PostgresSettingsReader(session)

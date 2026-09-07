import dishka
from dishka import Provider, Scope

from app.application.ports.persistence.readers.profiles import (
    ProfileReaderProtocol,
)
from app.application.ports.persistence.readers.settings import (
    SettingsReaderProtocol,
)
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


class QueriesProvider(Provider):
    scope = Scope.REQUEST

    @dishka.provide
    def get_my_profile(self, reader: ProfileReaderProtocol) -> GetMyProfileHandler:
        return GetMyProfileHandler(reader)

    @dishka.provide
    def get_public_profile(
        self, profiles: ProfileReaderProtocol, settings: SettingsReaderProtocol
    ) -> GetPublicProfileHandler:
        return GetPublicProfileHandler(profiles=profiles, settings=settings)

    @dishka.provide
    def search_by_username(
        self, profiles: ProfileReaderProtocol, settings: SettingsReaderProtocol
    ) -> SearchByUsernameHandler:
        return SearchByUsernameHandler(profiles=profiles, settings=settings)

    @dishka.provide
    def get_batch_profiles(
        self, profiles: ProfileReaderProtocol, settings: SettingsReaderProtocol
    ) -> GetBatchProfilesHandler:
        return GetBatchProfilesHandler(profiles=profiles, settings=settings)

    @dishka.provide
    def check_exists(self, reader: ProfileReaderProtocol) -> CheckProfileExistsHandler:
        return CheckProfileExistsHandler(reader)

    @dishka.provide
    def get_my_settings(self, reader: SettingsReaderProtocol) -> GetMySettingsHandler:
        return GetMySettingsHandler(reader)

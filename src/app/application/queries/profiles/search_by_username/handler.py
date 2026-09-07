from app.application.dto.profiles import PublicProfileDTO
from app.application.ports.persistence.readers.profiles import ProfileReaderProtocol
from app.application.ports.persistence.readers.settings import SettingsReaderProtocol
from app.application.queries.profiles.search_by_username.query import (
    SearchByUsernameQuery,
)
from app.domain.exceptions.user_profile import UserProfileNotFoundError
from app.domain.exceptions.user_settings import UserSettingsNotFoundError
from app.domain.policies.privacy import ProfilePrivacyPolicy
from app.domain.value_objects.username import Username


class SearchByUsernameHandler:
    def __init__(
        self, profiles: ProfileReaderProtocol, settings: SettingsReaderProtocol
    ) -> None:
        self._profiles = profiles
        self._settings = settings

    async def __call__(self, query: SearchByUsernameQuery) -> PublicProfileDTO:
        profile = await self._profiles.get_by_username(Username(query.username))
        if profile is None:
            raise UserProfileNotFoundError()
        settings = await self._settings.get_by_id(profile.user_id)
        if settings is None:
            raise UserSettingsNotFoundError()
        if not ProfilePrivacyPolicy.can_find_by_username(
            profile.user_id, settings, query.viewer_id
        ):
            # Скрытый и отсутствующий username дают одинаковый результат поиска.
            raise UserProfileNotFoundError()
        return PublicProfileDTO.from_domain_with_policy(
            profile, settings, query.viewer_id
        )

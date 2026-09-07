from app.application.dto.profiles import PublicProfileDTO
from app.application.ports.persistence.readers.profiles import ProfileReaderProtocol
from app.application.ports.persistence.readers.settings import SettingsReaderProtocol
from app.application.queries.profiles.get_public.query import GetPublicProfileQuery
from app.domain.exceptions.user_profile import UserProfileNotFoundError
from app.domain.exceptions.user_settings import UserSettingsNotFoundError


class GetPublicProfileHandler:
    def __init__(
        self, profiles: ProfileReaderProtocol, settings: SettingsReaderProtocol
    ) -> None:
        self._profiles = profiles
        self._settings = settings

    async def __call__(self, query: GetPublicProfileQuery) -> PublicProfileDTO:
        profile = await self._profiles.get_by_id(query.user_id)
        if profile is None:
            raise UserProfileNotFoundError()
        settings = await self._settings.get_by_id(profile.user_id)
        if settings is None:
            # Без настроек нельзя определить видимость приватных полей.
            raise UserSettingsNotFoundError()
        return PublicProfileDTO.from_domain_with_policy(
            profile, settings, query.viewer_id
        )

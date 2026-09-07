from app.application.dto.profiles import PublicProfileDTO
from app.application.ports.persistence.readers.profiles import ProfileReaderProtocol
from app.application.ports.persistence.readers.settings import SettingsReaderProtocol
from app.application.queries.profiles.get_batch.query import GetBatchProfilesQuery
from app.domain.exceptions.user_settings import UserSettingsNotFoundError


class GetBatchProfilesHandler:
    def __init__(
        self, profiles: ProfileReaderProtocol, settings: SettingsReaderProtocol
    ) -> None:
        self._profiles = profiles
        self._settings = settings

    async def __call__(self, query: GetBatchProfilesQuery) -> list[PublicProfileDTO]:
        profiles = await self._profiles.get_batch(query.user_ids)
        by_id = {profile.user_id: profile for profile in profiles}
        result: list[PublicProfileDTO] = []
        for user_id in query.user_ids:
            profile = by_id.get(user_id)
            if profile is None:
                continue
            # Reader settings пока имеет только get_by_id. Последовательные вызовы
            # совместимы и с адаптерами, использующими одну AsyncSession.
            settings = await self._settings.get_by_id(user_id)
            if settings is None:
                raise UserSettingsNotFoundError()
            result.append(
                PublicProfileDTO.from_domain_with_policy(
                    profile, settings, query.viewer_id
                )
            )
        return result

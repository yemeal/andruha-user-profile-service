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
        if not profiles:
            return []

        profiles_by_id = {profile.user_id: profile for profile in profiles}

        found_user_ids = (
            query.user_ids
            if len(profiles) == len(query.user_ids)
            else [uid for uid in query.user_ids if uid in profiles_by_id]
        )

        # Пакетная выборка настроек устраняет проблему N+1 запросов к базе данных.
        settings_list = await self._settings.get_batch(found_user_ids)
        settings_by_id = {settings.id: settings for settings in settings_list}

        if len(settings_by_id) != len(found_user_ids):
            raise UserSettingsNotFoundError()

        viewer_id = query.viewer_id

        return [
            PublicProfileDTO.from_domain_with_policy(
                profiles_by_id[uid], settings_by_id[uid], viewer_id
            )
            for uid in found_user_ids
        ]

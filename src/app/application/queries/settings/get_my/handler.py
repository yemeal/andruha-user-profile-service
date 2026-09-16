from app.application.dto.settings import SettingsDTO
from app.application.ports.persistence.readers.settings import SettingsReaderProtocol
from app.application.queries.settings.get_my.query import GetMySettingsQuery
from app.domain.exceptions.user_settings import UserSettingsNotFoundError


class GetMySettingsHandler:
    def __init__(self, settings: SettingsReaderProtocol) -> None:
        self._settings = settings

    async def __call__(self, query: GetMySettingsQuery) -> SettingsDTO:
        settings = await self._settings.get_by_id(query.user_id)
        if settings is None:
            raise UserSettingsNotFoundError()
        return SettingsDTO.from_domain(settings)

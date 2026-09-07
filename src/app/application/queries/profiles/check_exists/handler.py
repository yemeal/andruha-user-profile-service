from app.application.ports.persistence.readers.profiles import ProfileReaderProtocol
from app.application.queries.profiles.check_exists.query import CheckProfileExistsQuery


class CheckProfileExistsHandler:
    def __init__(self, profiles: ProfileReaderProtocol) -> None:
        self._profiles = profiles

    async def __call__(self, query: CheckProfileExistsQuery) -> bool:
        return await self._profiles.exists(query.user_id)

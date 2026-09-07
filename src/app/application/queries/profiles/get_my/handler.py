from app.application.dto.profiles import ProfileDTO
from app.application.ports.persistence.readers.profiles import ProfileReaderProtocol
from app.application.queries.profiles.get_my.query import GetMyProfileQuery
from app.domain.exceptions.user_profile import UserProfileNotFoundError


class GetMyProfileHandler:
    def __init__(self, profiles: ProfileReaderProtocol) -> None:
        self._profiles = profiles

    async def __call__(self, query: GetMyProfileQuery) -> ProfileDTO:
        profile = await self._profiles.get_by_id(query.user_id)
        if profile is None:
            raise UserProfileNotFoundError()
        return ProfileDTO.from_domain(profile)

from collections.abc import Callable
from datetime import datetime

from app.application.commands.profiles.update import UpdateProfileCommand
from app.application.dto.profiles import ProfileDTO
from app.application.ports.persistence.repositories import ProfileRepositoryProtocol
from app.domain.exceptions import ProfileVersionMismatchError, UserProfileNotFoundError


class UpdateProfileHandler:
    def __init__(
        self,
        profiles: ProfileRepositoryProtocol,
        clock: Callable[[], datetime],
    ) -> None:
        self._profiles = profiles
        self._clock = clock

    async def __call__(self, command: UpdateProfileCommand) -> ProfileDTO:
        profile = await self._profiles.get_by_id(command.user_id)

        if profile is None:
            raise UserProfileNotFoundError()

        if profile.version != command.expected_version:
            raise ProfileVersionMismatchError()

        changed = profile.update_profile(
            now=self._clock(),
            display_name=command.display_name,
            bio=command.bio,
            username=command.username,
        )

        if changed:
            profile = await self._profiles.update(
                profile,
                expected_version=command.expected_version,
            )

        return ProfileDTO.from_domain(profile)

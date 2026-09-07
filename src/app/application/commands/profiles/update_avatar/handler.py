from collections.abc import Callable
from datetime import datetime

from app.application.commands.profiles.update_avatar import UpdateAvatarCommand
from app.application.dto import ProfileDTO
from app.application.ports.persistence import ProfileRepositoryProtocol
from app.domain.exceptions import ProfileVersionMismatchError, UserProfileNotFoundError


class UpdateAvatarHandler:
    def __init__(
        self, profiles: ProfileRepositoryProtocol, clock: Callable[[], datetime]
    ) -> None:
        self._profiles = profiles
        self._clock = clock

    async def __call__(self, command: UpdateAvatarCommand) -> ProfileDTO:
        profile = await self._profiles.get_by_id(command.user_id)

        if profile is None:
            raise UserProfileNotFoundError()

        if profile.version != command.expected_version:
            raise ProfileVersionMismatchError()

        changed = profile.update_avatar(
            avatar_key=command.avatar_key,
            now=self._clock(),
        )

        if changed:
            profile = await self._profiles.update(
                profile,
                expected_version=command.expected_version,
            )

        return ProfileDTO.from_domain(profile)

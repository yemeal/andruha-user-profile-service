from collections.abc import Callable
from datetime import datetime

from app.application.commands.settings.update import UpdateSettingsCommand
from app.application.dto import SettingsDTO
from app.application.ports.persistence.repositories import SettingsRepositoryProtocol
from app.domain.exceptions import (
    SettingsVersionMismatchError,
    UserSettingsNotFoundError,
)
from app.domain.value_objects import PrivacySettings


class UpdateSettingsHandler:
    def __init__(
        self,
        settings: SettingsRepositoryProtocol,
        clock: Callable[[], datetime],
    ) -> None:
        self._settings = settings
        self._clock = clock

    async def __call__(self, command: UpdateSettingsCommand) -> SettingsDTO:
        settings = await self._settings.get_by_id(command.user_id)

        if settings is None:
            raise UserSettingsNotFoundError()

        if settings.version != command.expected_version:
            raise SettingsVersionMismatchError(current_version=settings.version)

        privacy = PrivacySettings(
            who_can_see_avatar=(
                command.who_can_see_avatar
                if command.who_can_see_avatar is not None
                else settings.privacy.who_can_see_avatar
            ),
            who_can_find_by_username=(
                command.who_can_find_by_username
                if command.who_can_find_by_username is not None
                else settings.privacy.who_can_find_by_username
            ),
            who_can_see_bio=(
                command.who_can_see_bio
                if command.who_can_see_bio is not None
                else settings.privacy.who_can_see_bio
            ),
        )
        changed = settings.update_settings(
            theme=command.theme,
            locale=command.locale,
            timezone=command.timezone,
            privacy=privacy,
            now=self._clock(),
        )

        if changed:
            settings = await self._settings.update(
                settings,
                expected_version=command.expected_version,
            )

        return SettingsDTO.from_domain(settings)

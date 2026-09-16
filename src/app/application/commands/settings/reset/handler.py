from collections.abc import Callable
from datetime import datetime

from app.application.commands.settings.reset import ResetSettingsCommand
from app.application.dto import SettingsDTO
from app.application.ports.persistence.repositories import SettingsRepositoryProtocol
from app.domain.exceptions import (
    SettingsVersionMismatchError,
    UserSettingsNotFoundError,
)


class ResetSettingsHandler:
    def __init__(
        self, settings: SettingsRepositoryProtocol, clock: Callable[[], datetime]
    ) -> None:
        self._settings = settings
        self._clock = clock

    async def __call__(self, command: ResetSettingsCommand) -> SettingsDTO:
        settings = await self._settings.get_by_id(command.user_id)

        if settings is None:
            raise UserSettingsNotFoundError()

        if settings.version != command.expected_version:
            raise SettingsVersionMismatchError()

        changed = settings.reset_to_defaults(now=self._clock())

        if changed:
            settings = await self._settings.update(
                settings,
                expected_version=command.expected_version,
            )

        return SettingsDTO.from_domain(settings)

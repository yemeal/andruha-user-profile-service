from app.application.commands.profiles.create_default.command import (
    CreateDefaultProfileCommand,
)
from app.application.ports.persistence.repositories import (
    ProfileRepositoryProtocol,
    SettingsRepositoryProtocol,
)


class CreateDefaultProfileHandler:
    """Обработчик команды создания дефолтного профиля и настроек пользователя."""

    def __init__(
        self,
        profiles: ProfileRepositoryProtocol,
        settings: SettingsRepositoryProtocol,
    ) -> None:
        self._profiles = profiles
        self._settings = settings

    async def __call__(self, command: CreateDefaultProfileCommand) -> None:
        await self._profiles.create_default_if_absent(
            user_id=command.user_id,
            now=command.registered_at,
        )
        await self._settings.create_default_if_absent(
            user_id=command.user_id,
            now=command.registered_at,
        )

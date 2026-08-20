import uuid

from pydantic import Field

from app.application.dto.base import BaseCommand


class UpdateSettingsCommand(BaseCommand):
    """
    Команда обновления настроек интерфейса и приватности пользователя.
    """

    user_id: uuid.UUID = Field(
        description="Идентификатор пользователя (UUIDv7)",
    )
    expected_version: int = Field(
        ge=1,
        description="Ожидаемый номер версии настроек для оптимистической блокировки (OCC)",
    )
    theme: str | None = Field(
        default=None,
        description="Новая тема оформления интерфейса (light, dark, system)",
    )
    locale: str | None = Field(
        default=None,
        description="Новый язык локализации (ru, en)",
    )
    timezone: str | None = Field(
        default=None,
        description="Новый часовой пояс пользователя по IANA",
    )
    who_can_see_avatar: str | None = Field(
        default=None,
        description="Кто может видеть аватар профиля (ALL, NOBODY)",
    )
    who_can_find_by_username: str | None = Field(
        default=None,
        description="Кто может находить профиль в поиске по username (ALL, NOBODY)",
    )
    who_can_see_bio: str | None = Field(
        default=None,
        description="Кто может видеть описание/био профиля (ALL, NOBODY)",
    )

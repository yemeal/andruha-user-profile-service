import uuid

from pydantic import Field

from app.application.commands.base import BaseCommand


class UpdateProfileCommand(BaseCommand):
    """
    Команда обновления изменяемых текстовых полей профиля пользователя.
    """

    user_id: uuid.UUID = Field(
        description="Идентификатор обновляемого пользователя (UUIDv7)",
    )
    expected_version: int = Field(
        ge=1,
        description="Ожидаемый номер версии профиля для оптимистической блокировки (OCC)",
    )
    display_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="Новое отображаемое имя профиля (1..64 символа, без эмодзи)",
    )
    bio: str | None = Field(
        default=None,
        max_length=255,
        description="Новое краткое описание/биография профиля (до 255 символов, одна строка)",
    )
    username: str | None = Field(
        default=None,
        min_length=3,
        max_length=32,
        description="Новый уникальный публичный никнейм ([a-z0-9_]{3,32})",
    )

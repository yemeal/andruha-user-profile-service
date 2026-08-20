import uuid

from pydantic import Field

from app.application.dto.base import BaseCommand


class UpdateAvatarCommand(BaseCommand):
    """
    Команда обновления или удаления аватара профиля пользователя.
    """

    user_id: uuid.UUID = Field(
        description="Идентификатор пользователя (UUIDv7)",
    )
    expected_version: int = Field(
        ge=1,
        description="Ожидаемый номер версии профиля для оптимистической блокировки (OCC)",
    )
    avatar_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=512,
        description="Ключ к аватару в объектном хранилище (None для удаления)",
    )

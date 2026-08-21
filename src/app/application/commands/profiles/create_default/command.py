import uuid

from pydantic import AwareDatetime, Field

from app.application.commands.base import BaseCommand


class CreateDefaultProfileCommand(BaseCommand):
    """
    Команда создания дефолтного профиля и настроек пользователя.
    Используется при обработке входящих событий регистрации и в механизме Lazy JIT Repair.
    """

    user_id: uuid.UUID = Field(
        description="Уникальный идентификатор пользователя (UUIDv7)",
    )
    registered_at: AwareDatetime = Field(
        description="Метка времени регистрации пользователя с обязательной таймзоной (UTC)",
    )
    event_id: uuid.UUID | None = Field(
        default=None,
        description="Идентификатор входящего события для защиты от повторной обработки (Inbox fence)",
    )

from typing import Protocol
from uuid import UUID

from app.application.ports.persistence.readers.base import AsyncReaderProtocol
from app.domain.aggregates.settings import UserSettings


class SettingsReaderProtocol(AsyncReaderProtocol[UserSettings, UUID], Protocol):
    """
    Порт чтения данных настроек пользователя (Read Side / Projections).
    Поддерживает get_by_id, get_batch и exists.
    """

    ...

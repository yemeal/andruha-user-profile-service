import uuid
from datetime import datetime

from pydantic import Field

from app.application.queries.base import BaseQueryResult
from app.domain.value_objects.locale import Locale
from app.domain.value_objects.privacy import PrivacySettings
from app.domain.value_objects.theme import Theme


class SettingsDTO(BaseQueryResult):
    """
    Представление настроек интерфейса и приватности пользователя.
    """

    user_id: uuid.UUID = Field(
        description="Уникальный идентификатор пользователя (UUIDv7)",
    )
    theme: Theme = Field(
        description="Тема оформления интерфейса (light, dark, system)",
    )
    locale: Locale = Field(
        description="Язык интерфейса (ru, en)",
    )
    timezone: str = Field(
        description="Часовой пояс по IANA",
    )
    privacy: PrivacySettings = Field(
        description="Составные настройки приватности профиля",
    )
    version: int = Field(
        description="Текущий номер версии настроек для оптимистической блокировки (OCC)",
    )
    created_at: datetime = Field(
        description="Дата создания настроек (UTC)",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="Дата последнего обновления настроек (UTC)",
    )


MySettingsResult = SettingsDTO

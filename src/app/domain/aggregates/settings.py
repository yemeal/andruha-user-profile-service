import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.domain.base import VersionedMutableEntity
from app.domain.value_objects.locale import Locale
from app.domain.value_objects.privacy import PrivacySettings
from app.domain.value_objects.theme import Theme
from app.domain.value_objects.timezone import DEFAULT_TIMEZONE, Timezone


class UserSettings(VersionedMutableEntity):
    """Агрегат настроек пользователя (UserSettings Aggregate Root)."""

    id: uuid.UUID = Field(
        frozen=True,
        validation_alias="user_id",
        default_factory=uuid.uuid7,
        description="Уникальный идентификатор пользователя (UUIDv7)",
    )
    theme: Theme = Field(
        frozen=True,
        default_factory=Theme.default,
        description="Тема оформления пользовательского интерфейса",
    )
    locale: Locale = Field(
        frozen=True,
        default_factory=Locale.default,
        description="Язык локализации интерфейса",
    )
    timezone: Timezone = Field(
        frozen=True,
        default=DEFAULT_TIMEZONE,
        description="Часовой пояс пользователя по базе данных IANA",
    )
    privacy: PrivacySettings = Field(
        frozen=True,
        default_factory=PrivacySettings.default,
        description="Составные настройки приватности профиля",
    )

    @property
    def user_id(self) -> uuid.UUID:
        """Псевдоним id для агрегата настроек пользователя."""
        return self.id

    @classmethod
    def create_default(cls, user_id: uuid.UUID, now: datetime) -> UserSettings:
        """Фабрика для создания дефолтных настроек пользователя."""
        return cls(
            id=user_id,
            theme=Theme.default(),
            locale=Locale.default(),
            timezone=DEFAULT_TIMEZONE,
            privacy=PrivacySettings.default(),
            version=1,
            created_at=now,
            updated_at=None,
        )

    def update_settings(
        self,
        *,
        theme: Theme | str | None = None,
        locale: Locale | str | None = None,
        timezone: Timezone | str | None = None,
        privacy: PrivacySettings | dict[str, Any] | None = None,
        now: datetime,
    ) -> bool:
        """Обновляет настройки пользователя. Возвращает True, если было реальное изменение."""
        return self._apply_changes(
            now=now,
            theme=self.theme if theme is None else theme,
            locale=self.locale if locale is None else locale,
            timezone=self.timezone if timezone is None else timezone,
            privacy=self.privacy if privacy is None else privacy,
        )

    def reset_to_defaults(self, now: datetime) -> bool:
        """Сбрасывает все настройки интерфейса к дефолтным значениям."""
        return self.update_settings(
            theme=Theme.default(),
            locale=Locale.default(),
            timezone=DEFAULT_TIMEZONE,
            privacy=PrivacySettings.default(),
            now=now,
        )

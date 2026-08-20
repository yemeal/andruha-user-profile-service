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
        validation_alias="user_id",
        default_factory=uuid.uuid7,
        description="Уникальный идентификатор пользователя (UUIDv7)",
    )
    theme: Theme = Field(
        default_factory=Theme.default,
        description="Тема оформления пользовательского интерфейса",
    )
    locale: Locale = Field(
        default_factory=Locale.default,
        description="Язык локализации интерфейса",
    )
    timezone: Timezone = Field(
        default=DEFAULT_TIMEZONE,
        description="Часовой пояс пользователя по базе данных IANA",
    )
    privacy: PrivacySettings = Field(
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
        changed = False

        if theme is not None:
            candidate_theme = Theme(theme)
            if candidate_theme != self.theme:
                self.theme = candidate_theme
                changed = True

        if locale is not None:
            candidate_locale = Locale(locale)
            if candidate_locale != self.locale:
                self.locale = candidate_locale
                changed = True

        if timezone is not None and timezone.strip() != self.timezone:
            self.timezone = timezone
            changed = True

        if privacy is not None:
            candidate_privacy = (
                privacy
                if isinstance(privacy, PrivacySettings)
                else PrivacySettings.model_validate(privacy)
            )
            if candidate_privacy != self.privacy:
                self.privacy = candidate_privacy
                changed = True

        if changed:
            self.mark_updated(now)

        return changed

    def reset_to_defaults(self, now: datetime) -> bool:
        """Сбрасывает все настройки интерфейса к дефолтным значениям."""
        return self.update_settings(
            theme=Theme.default(),
            locale=Locale.default(),
            timezone=DEFAULT_TIMEZONE,
            privacy=PrivacySettings.default(),
            now=now,
        )

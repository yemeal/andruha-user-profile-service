from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.domain.exceptions.user_settings import InvalidPrivacyScopeError


class PrivacyScope(StrEnum):
    """
    Область видимости настроек приватности.

    Допустимые значения:

    - ALL ('ALL'): доступно всем пользователям;
    - NOBODY ('NOBODY'): скрыто от всех пользователей.
    """

    ALL = "ALL"
    NOBODY = "NOBODY"

    @classmethod
    def _missing_(cls, value: object) -> PrivacyScope:
        raise InvalidPrivacyScopeError()


class PrivacySettings(BaseModel):
    """
    Агрегированные настройки приватности профиля пользователя (Value Object).

    Поля:

    - who_can_see_avatar: кто может видеть фотографию/аватар профиля (по умолчанию ALL);
    - who_can_find_by_username: кто может находить профиль по username через поиск (по умолчанию ALL);
    - who_can_see_bio: кто может читать описание профиля (по умолчанию ALL).
    """

    model_config = ConfigDict(
        frozen=True, extra="forbid", from_attributes=True, validate_assignment=True
    )

    who_can_see_avatar: PrivacyScope = PrivacyScope.ALL
    who_can_find_by_username: PrivacyScope = PrivacyScope.ALL
    who_can_see_bio: PrivacyScope = PrivacyScope.ALL

    @classmethod
    def default(cls) -> PrivacySettings:
        return cls()

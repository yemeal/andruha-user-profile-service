from enum import StrEnum

from app.domain.exceptions.user_profile import InvalidProfileStatusError


class UserProfileStatus(StrEnum):
    """
    Статус жизненного цикла профиля пользователя.

    Допустимые значения:
    - ACTIVE ('ACTIVE'): активный профиль;
    - DISABLED ('DISABLED'): отключён пользователем;
    - BLOCKED ('BLOCKED'): заблокирован администрацией.
    """

    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    BLOCKED = "BLOCKED"

    @classmethod
    def _missing_(cls, value: object) -> UserProfileStatus:
        raise InvalidProfileStatusError()

    @classmethod
    def default(cls) -> UserProfileStatus:
        return cls.ACTIVE

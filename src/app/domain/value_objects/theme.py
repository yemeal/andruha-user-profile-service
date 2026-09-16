from enum import StrEnum

from app.domain.exceptions.user_settings import InvalidThemeError


class Theme(StrEnum):
    """
    Тема оформления интерфейса пользователя.

    Допустимые значения:

    - SYSTEM ('system'): следовать системной теме устройства (по умолчанию);
    - LIGHT ('light'): светлая тема;
    - DARK ('dark'): тёмная тема.
    """

    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"

    # Когда Theme(...) не находит переданное значение среди допустимых,
    # Python автоматически вызывает этот метод, и мы выбрасываем наше строго типизированное доменное исключение
    # InvalidThemeError вместо ValueError.
    @classmethod
    def _missing_(cls, value: object) -> Theme:
        raise InvalidThemeError()

    @classmethod
    def default(cls) -> Theme:
        return cls.SYSTEM

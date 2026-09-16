from enum import StrEnum

from app.domain.exceptions.user_settings import InvalidLocaleError


class Locale(StrEnum):
    """
    Язык локализации интерфейса пользователя.

    Допустимые значения:

    - RU ('ru'): русский язык (по умолчанию);
    - EN ('en'): английский язык.
    """

    RU = "ru"
    EN = "en"

    # Когда Locale(...) не находит переданное значение среди допустимых (ru, en),
    # Python автоматически вызывает этот метод, и мы выбрасываем наше строго типизированное доменное исключение
    # InvalidLocaleError вместо ValueError.
    @classmethod
    def _missing_(cls, value: object) -> Locale:
        raise InvalidLocaleError()

    @classmethod
    def default(cls) -> Locale:
        return cls.RU

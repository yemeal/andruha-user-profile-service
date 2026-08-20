import re
from typing import Annotated

from pydantic import AfterValidator

from app.domain.exceptions.user_profile import InvalidDisplayNameError

DEFAULT_DISPLAY_NAME: str = "Пользователь"

_EMOJI_REGEX = re.compile(r"[\u2600-\u27BF\U0001F000-\U0001FFFF]")


def _contains_emoji(text: str) -> bool:
    """
    Проверяет наличие эмодзи:

    - Fast path: если все символы базовые (ASCII/кириллица < 0x2000), эмодзи гарантированно нет;
    - Slow path: поиск через скомпилированный C-регулярный движок.
    """
    if max(text) < "\u2000":
        return False

    return _EMOJI_REGEX.search(text) is not None


def _validate_display_name(value: str) -> str:
    """Валидатор для отображаемого имени пользователя"""
    if not isinstance(value, str):
        raise InvalidDisplayNameError()

    trimmed = value.strip()
    if not (1 <= len(trimmed) <= 64):
        raise InvalidDisplayNameError()

    if _contains_emoji(trimmed):
        raise InvalidDisplayNameError()

    return trimmed


DisplayName = Annotated[
    str,
    AfterValidator(_validate_display_name),
]
"""
Отображаемое имя пользователя

Инварианты:

- Длина: от 1 до 64 символов;
- Автоматический тримминг пробелов по краям;
- Запрет пустых строк и строк только из пробелов;
- Запрет эмодзи и специальных символов-пиктограмм;
- Значение по умолчанию: 'Пользователь'.
"""

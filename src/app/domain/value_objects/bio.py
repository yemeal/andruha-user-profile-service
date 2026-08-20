from typing import Annotated

from pydantic import AfterValidator

from app.domain.exceptions.user_profile import InvalidBioError


def _validate_bio(value: str) -> str:
    """Валидатор для описания профиля (bio)"""
    if not isinstance(value, str):
        raise InvalidBioError()

    if len(value) > 255:
        raise InvalidBioError()

    if "\n" in value or "\r" in value:
        raise InvalidBioError()

    return value


Bio = Annotated[
    str,
    AfterValidator(_validate_bio),
]
"""
Краткое описание профиля

Инварианты:

- Максимальная длина: 255 символов;
- Запрещены переносы строк;
- Является опциональным полем профиля (None).
"""

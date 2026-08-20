import re
from typing import Any

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema

from app.domain.exceptions.user_profile import (
    InvalidUsernameError,
    ReservedUsernameError,
)

RESERVED_USERNAMES: frozenset[str] = frozenset(
    {
        "admin",
        "administrator",
        "root",
        "system",
        "support",
        "help",
        "api",
        "bot",
        "official",
        "andruha",
        "moderator",
        "service",
        "null",
        "undefined",
    }
)

_USERNAME_REGEX = re.compile(r"^[a-z0-9_]{3,32}$")


# Реализация такая чисто для того, чтобы понять как делать валидацию без Pydantic + Annotated
class Username(str):
    """
    Value object для username пользователя.

    Инварианты:
    - Только латиница в нижнем регистре, цифры и символ подчеркивания (^[a-z0-9_]{3,32}$);
    - Длина: от 3 до 32 символов;
    - Запрет зарезервированных системных имен (admin, system, support, andruha и др.);
    - Регистронезависимый (хранится строго в нижнем регистре).
    """

    def __new__(cls, value: str) -> Username:
        if not isinstance(value, str):
            raise InvalidUsernameError()

        normalized = value.strip().lower()

        if not _USERNAME_REGEX.fullmatch(normalized):
            raise InvalidUsernameError()

        if normalized in RESERVED_USERNAMES:
            raise ReservedUsernameError()

        # noinspection PyTypeChecker
        return super().__new__(cls, normalized)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        """Pydantic V2 core schema integration."""
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(),
        )

import zoneinfo
from typing import Annotated

from pydantic import AfterValidator

from app.domain.exceptions.user_settings import InvalidTimezoneError

DEFAULT_TIMEZONE: str = "Europe/Moscow"


def _validate_timezone(value: str) -> str:
    """Валидатор для IANA часового пояса"""
    if not isinstance(value, str):
        raise InvalidTimezoneError()

    normalized = value.strip()
    try:
        zoneinfo.ZoneInfo(normalized)
    except Exception:
        raise InvalidTimezoneError() from None

    return normalized


Timezone = Annotated[
    str,
    AfterValidator(_validate_timezone),
]
"""
Идентификатор IANA часового пояса (Timezone).

Инварианты:
- Должен являться валидным идентификатором временной зоны из базы tzdata (например, 'Europe/Moscow', 'UTC');
- Значение по умолчанию: 'Europe/Moscow'.
"""

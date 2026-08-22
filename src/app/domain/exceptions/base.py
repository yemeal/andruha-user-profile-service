from typing import ClassVar


class DomainError(Exception):
    """Базовый тип ожидаемых ошибок домена."""

    default_message: ClassVar[str] = "Domain error"

    def __init__(self) -> None:
        super().__init__(self.default_message)


class InvalidTimestampError(DomainError):
    """Время обновления (updated_at) должно быть строго позже времени создания (created_at)."""

    default_message: ClassVar[str] = (
        "updated_at must be strictly greater than created_at"
    )

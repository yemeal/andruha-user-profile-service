from app.domain.exceptions.base import DomainError


class UserSettingsError(DomainError): ...


class InvalidThemeError(UserSettingsError): ...


class InvalidLocaleError(UserSettingsError): ...


class InvalidTimezoneError(UserSettingsError): ...


class InvalidPrivacyScopeError(UserSettingsError): ...


class UserSettingsNotFoundError(UserSettingsError): ...


class SettingsVersionMismatchError(UserSettingsError):
    def __init__(self, *, current_version: int | None = None) -> None:
        super().__init__()
        self.current_version = current_version

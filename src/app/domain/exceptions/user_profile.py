from app.domain.exceptions.base import DomainError


class UserProfileError(DomainError): ...


class UsernameError(UserProfileError): ...


class UsernameAlreadyTakenError(UsernameError): ...


class InvalidUsernameError(UsernameError): ...


class ReservedUsernameError(UsernameError): ...


class InvalidDisplayNameError(UserProfileError): ...


class InvalidBioError(UserProfileError): ...


class UserProfileNotFoundError(UserProfileError): ...


class ProfileVersionMismatchError(UserProfileError):
    def __init__(self, *, current_version: int | None = None) -> None:
        super().__init__()
        self.current_version = current_version


class InvalidProfileStatusError(UserProfileError): ...

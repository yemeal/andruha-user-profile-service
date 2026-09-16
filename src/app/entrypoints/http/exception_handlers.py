"""Translate profile read failures into safe HTTP responses."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.application.exceptions.idempotency import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
    IdempotencyKeyRequiredError,
    IdempotencyUnavailableError,
    StoredReplayUnavailableError,
)
from app.application.exceptions.persistence import (
    PersistenceUnavailableError,
    TransactionConflictError,
)
from app.domain.exceptions import (
    InvalidBioError,
    InvalidDisplayNameError,
    InvalidLocaleError,
    InvalidPrivacyScopeError,
    InvalidThemeError,
    InvalidTimezoneError,
    InvalidUsernameError,
    ProfileVersionMismatchError,
    ReservedUsernameError,
    SettingsVersionMismatchError,
    UsernameAlreadyTakenError,
)
from app.domain.exceptions.user_profile import UserProfileNotFoundError
from app.domain.exceptions.user_settings import UserSettingsNotFoundError


def version_conflict(_request: Request, error: Exception) -> JSONResponse:
    assert isinstance(
        error, (ProfileVersionMismatchError, SettingsVersionMismatchError)
    )
    parameters = (
        {}
        if error.current_version is None
        else {"current_version": error.current_version}
    )
    return JSONResponse(
        status_code=409,
        content={"detail": "Version conflict", "parameters": parameters},
        headers={"Cache-Control": "no-store"},
    )


def invalid_input(_request: Request, _error: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid request value"},
        headers={"Cache-Control": "no-store"},
    )


def conflict(_request: Request, error: Exception) -> JSONResponse:
    detail = (
        "Username already taken"
        if isinstance(error, UsernameAlreadyTakenError)
        else "Idempotency key conflict"
    )
    return JSONResponse(
        status_code=409,
        content={"detail": detail},
        headers={"Cache-Control": "no-store"},
    )


def in_progress(_request: Request, _error: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"detail": "Request is in progress"},
        headers={"Retry-After": "1", "Cache-Control": "no-store"},
    )


def profile_not_found(_request: Request, _error: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"detail": "Profile not found"},
        headers={"Cache-Control": "no-store"},
    )


def profile_unavailable(_request: Request, _error: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "Profile temporarily unavailable"},
        headers={"Cache-Control": "no-store"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(UserProfileNotFoundError, profile_not_found)
    app.add_exception_handler(UserSettingsNotFoundError, profile_unavailable)
    app.add_exception_handler(PersistenceUnavailableError, profile_unavailable)
    for error in (
        IdempotencyUnavailableError,
        StoredReplayUnavailableError,
        TransactionConflictError,
    ):
        app.add_exception_handler(error, profile_unavailable)
    for error in (ProfileVersionMismatchError, SettingsVersionMismatchError):
        app.add_exception_handler(error, version_conflict)
    for error in (
        InvalidDisplayNameError,
        InvalidBioError,
        InvalidUsernameError,
        ReservedUsernameError,
        InvalidLocaleError,
        InvalidThemeError,
        InvalidTimezoneError,
        InvalidPrivacyScopeError,
        IdempotencyKeyRequiredError,
    ):
        app.add_exception_handler(error, invalid_input)
    app.add_exception_handler(UsernameAlreadyTakenError, conflict)
    app.add_exception_handler(IdempotencyConflictError, conflict)
    app.add_exception_handler(IdempotencyInProgressError, in_progress)

from collections.abc import Iterator
from contextlib import contextmanager
from typing import NoReturn

from sqlalchemy.exc import DBAPIError, DisconnectionError, SQLAlchemyError, TimeoutError

from app.application.exceptions.persistence import (
    PersistenceUnavailableError,
    TransactionConflictError,
)


def raise_persistence_error(error: SQLAlchemyError | OSError) -> NoReturn:
    """Translate availability/conflict failures while preserving SQL/data errors."""
    if isinstance(error, DBAPIError):
        sqlstate = getattr(error.orig, "sqlstate", None) or getattr(
            error.orig, "pgcode", None
        )
        if sqlstate in {"40001", "40P01"}:
            raise TransactionConflictError("Concurrent transaction conflict") from error
        if error.connection_invalidated or (sqlstate and sqlstate.startswith("08")):
            raise PersistenceUnavailableError(
                "Database connection unavailable"
            ) from error
    if isinstance(error, (OSError, DisconnectionError, TimeoutError)):
        raise PersistenceUnavailableError("Database unavailable") from error
    raise error


@contextmanager
def database_errors() -> Iterator[None]:
    try:
        yield
    except (SQLAlchemyError, OSError) as error:
        raise_persistence_error(error)

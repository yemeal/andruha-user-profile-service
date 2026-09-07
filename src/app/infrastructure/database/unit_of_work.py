from types import TracebackType
from typing import NoReturn, Self

from sqlalchemy.exc import DBAPIError, DisconnectionError, SQLAlchemyError, TimeoutError
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from app.application.exceptions.persistence import (
    PersistenceUnavailableError,
    TransactionConflictError,
)


def _raise_persistence_error(error: SQLAlchemyError) -> NoReturn:
    """Переводим только известные ошибки драйвера, не скрывая ошибки SQL/данных."""
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
    if isinstance(error, (DisconnectionError, TimeoutError)):
        raise PersistenceUnavailableError("Database unavailable") from error
    raise error


class SqlAlchemyUnitOfWork:
    """Владелец транзакции одной session; пригоден для последовательных контекстов."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._transaction: AsyncSessionTransaction | None = None

    async def __aenter__(self) -> Self:
        if self._transaction is not None or self._session.in_transaction():
            raise RuntimeError("Nested or shared UoW transaction is not allowed")
        transaction = self._session.begin()
        try:
            await transaction.__aenter__()
        except SQLAlchemyError as error:
            _raise_persistence_error(error)
        self._transaction = transaction
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        transaction = self._transaction
        if transaction is None:
            raise RuntimeError("UoW transaction has not been started")
        try:
            # SQLAlchemy commits success and rolls back every BaseException,
            # including asyncio.CancelledError.
            await transaction.__aexit__(exc_type, exc_val, exc_tb)
        except SQLAlchemyError as error:
            _raise_persistence_error(error)
        finally:
            self._transaction = None
        if isinstance(exc_val, SQLAlchemyError):
            _raise_persistence_error(exc_val)

from types import TracebackType
from typing import Self

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from app.infrastructure.database.errors import raise_persistence_error
from app.infrastructure.exceptions.database import (
    NestedTransactionNotAllowedError,
    TransactionNotStartedError,
)


class SqlAlchemyUnitOfWork:
    """Владелец транзакции одной session; пригоден для последовательных контекстов."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._transaction: AsyncSessionTransaction | None = None

    async def __aenter__(self) -> Self:
        if self._transaction is not None or self._session.in_transaction():
            raise NestedTransactionNotAllowedError()
        transaction = self._session.begin()
        try:
            await transaction.__aenter__()
        except (SQLAlchemyError, OSError) as error:
            raise_persistence_error(error)
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
            raise TransactionNotStartedError()
        try:
            # SQLAlchemy commits success and rolls back every BaseException,
            # including asyncio.CancelledError.
            await transaction.__aexit__(exc_type, exc_val, exc_tb)
        except (SQLAlchemyError, OSError) as error:
            raise_persistence_error(error)
        finally:
            self._transaction = None
        if isinstance(exc_val, (SQLAlchemyError, OSError)):
            raise_persistence_error(exc_val)

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError, TimeoutError

from app.application.exceptions.persistence import (
    PersistenceUnavailableError,
    TransactionConflictError,
)
from app.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork


def session():
    transaction = SimpleNamespace(__aenter__=AsyncMock(), __aexit__=AsyncMock())
    result = SimpleNamespace(begin=lambda: transaction, in_transaction=lambda: False)
    return result, transaction


async def test_success_and_cancellation_are_forwarded_to_transaction():
    db, transaction = session()
    uow = SqlAlchemyUnitOfWork(db)
    async with uow:
        pass
    transaction.__aexit__.assert_awaited_once_with(None, None, None)

    with pytest.raises(asyncio.CancelledError):
        async with uow:
            raise asyncio.CancelledError
    assert transaction.__aexit__.await_args.args[0] is asyncio.CancelledError


async def test_nested_transaction_is_rejected():
    db, _ = session()
    uow = SqlAlchemyUnitOfWork(db)
    async with uow:
        with pytest.raises(RuntimeError, match="Nested"):
            async with uow:
                pass


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("40001", TransactionConflictError),
        ("40P01", TransactionConflictError),
        ("08006", PersistenceUnavailableError),
    ],
)
async def test_known_database_errors_from_handler_are_mapped_after_rollback(
    state, expected
):
    class DriverError(Exception):
        sqlstate = state

    db, transaction = session()
    with pytest.raises(expected):
        async with SqlAlchemyUnitOfWork(db):
            raise DBAPIError("statement", {}, DriverError(), False)
    assert transaction.__aexit__.await_args.args[0] is DBAPIError


async def test_unrelated_integrity_error_is_not_misclassified_as_retryable():
    db, _ = session()
    error = IntegrityError("statement", {}, Exception("bad data"))
    with pytest.raises(IntegrityError) as caught:
        async with SqlAlchemyUnitOfWork(db):
            raise error
    assert caught.value is error


async def test_commit_failure_is_mapped_and_uow_state_is_released():
    db, transaction = session()
    uow = SqlAlchemyUnitOfWork(db)
    transaction.__aexit__.side_effect = TimeoutError("connection timeout")
    with pytest.raises(PersistenceUnavailableError):
        async with uow:
            pass
    transaction.__aexit__.side_effect = None
    async with uow:
        pass

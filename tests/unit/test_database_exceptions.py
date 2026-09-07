from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.infrastructure.database.repositories.profiles import (
    PostgresProfileRepository,
)
from app.infrastructure.exceptions.database import (
    DatabaseError,
    NestedTransactionNotAllowedError,
    TransactionError,
    TransactionNotStartedError,
    TransactionRequiredError,
)


def test_database_exception_hierarchy() -> None:
    assert issubclass(TransactionError, (DatabaseError, RuntimeError))
    assert issubclass(TransactionRequiredError, TransactionError)
    assert issubclass(NestedTransactionNotAllowedError, TransactionError)
    assert issubclass(TransactionNotStartedError, TransactionError)


async def test_repository_requires_transaction() -> None:
    mock_session = MagicMock()
    mock_session.in_transaction.return_value = False

    repo = PostgresProfileRepository(mock_session)

    with pytest.raises(TransactionRequiredError) as exc_info:
        await repo.get_by_id(uuid4())

    assert issubclass(TransactionRequiredError, RuntimeError)
    assert "explicit transaction" in str(exc_info.value)


async def test_repository_allows_call_in_transaction() -> None:
    mock_session = MagicMock()
    mock_session.in_transaction.return_value = True
    execute_result = MagicMock()
    execute_result.mappings.return_value.one_or_none.return_value = None
    mock_session.execute = MagicMock()

    async def _fake_execute(*args, **kwargs):
        return execute_result

    mock_session.execute.side_effect = _fake_execute

    repo = PostgresProfileRepository(mock_session)
    result = await repo.get_by_id(uuid4())
    assert result is None

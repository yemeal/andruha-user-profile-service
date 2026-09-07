from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.application.ports.persistence.readers.base import AsyncReaderProtocol
from app.application.ports.persistence.readers.profiles import (
    ProfileReaderProtocol,
)
from app.application.ports.persistence.readers.settings import (
    SettingsReaderProtocol,
)
from app.application.queries.profiles.get_batch.handler import (
    GetBatchProfilesHandler,
)
from app.application.queries.profiles.get_batch.query import (
    GetBatchProfilesQuery,
)
from app.domain.aggregates.profiles import UserProfile
from app.domain.aggregates.settings import UserSettings
from app.infrastructure.database.models.profiles import ProfileORM
from app.infrastructure.database.readers.base import BasePostgresReader
from app.infrastructure.database.readers.profiles import PostgresProfileReader
from app.infrastructure.database.readers.settings import PostgresSettingsReader


def test_reader_protocols_inheritance() -> None:
    assert AsyncReaderProtocol in ProfileReaderProtocol.__mro__
    assert AsyncReaderProtocol in SettingsReaderProtocol.__mro__


@pytest.mark.asyncio
async def test_base_postgres_reader_operates_without_transaction_requirement() -> None:
    session = MagicMock()
    session.in_transaction.return_value = False
    execute_result = MagicMock()
    execute_result.mappings.return_value.one_or_none.return_value = None
    execute_result.mappings.return_value.__iter__.return_value = []

    async def _fake_execute(*args, **kwargs):
        return execute_result

    session.execute.side_effect = _fake_execute
    session.scalar = AsyncMock(return_value=False)

    reader = BasePostgresReader[UserProfile](
        session=session,
        table=ProfileORM.__table__,
        aggregate=UserProfile,
    )

    # All read operations succeed without an active transaction
    assert await reader.get_by_id(uuid4()) is None
    assert await reader.exists(uuid4()) is False
    assert await reader.get_batch([uuid4()]) == []


@pytest.mark.asyncio
async def test_base_postgres_reader_empty_batch_skips_query() -> None:
    session = MagicMock()

    reader = BasePostgresReader[UserProfile](
        session=session,
        table=ProfileORM.__table__,
        aggregate=UserProfile,
    )

    result = await reader.get_batch([])
    assert result == []
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_postgres_profile_reader_inherits_base_and_has_username_lookup() -> None:
    session = MagicMock()
    reader = PostgresProfileReader(session)
    assert isinstance(reader, BasePostgresReader)
    assert hasattr(reader, "get_by_username")
    assert hasattr(reader, "get_by_id")
    assert hasattr(reader, "get_batch")
    assert hasattr(reader, "exists")


@pytest.mark.asyncio
async def test_postgres_settings_reader_inherits_base() -> None:
    session = MagicMock()
    reader = PostgresSettingsReader(session)
    assert isinstance(reader, BasePostgresReader)
    assert hasattr(reader, "get_by_id")
    assert hasattr(reader, "get_batch")
    assert hasattr(reader, "exists")


@pytest.mark.asyncio
async def test_get_batch_profiles_handler_eliminates_n_plus_1_queries() -> None:
    now = datetime(2026, 9, 8, tzinfo=UTC)
    uid1 = uuid4()
    uid2 = uuid4()

    profile1 = UserProfile.create_default(uid1, now)
    profile2 = UserProfile.create_default(uid2, now)
    settings1 = UserSettings.create_default(uid1, now)
    settings2 = UserSettings.create_default(uid2, now)

    mock_profile_reader = AsyncMock(spec=ProfileReaderProtocol)
    mock_profile_reader.get_batch.return_value = [profile1, profile2]

    mock_settings_reader = AsyncMock(spec=SettingsReaderProtocol)
    mock_settings_reader.get_batch.return_value = [settings1, settings2]

    handler = GetBatchProfilesHandler(
        profiles=mock_profile_reader,
        settings=mock_settings_reader,
    )

    query = GetBatchProfilesQuery(user_ids=[uid1, uid2])
    result = await handler(query)

    assert len(result) == 2
    mock_profile_reader.get_batch.assert_awaited_once_with([uid1, uid2])
    # Exactly ONE batch call for settings, not N calls to get_by_id!
    mock_settings_reader.get_batch.assert_awaited_once_with([uid1, uid2])
    mock_settings_reader.get_by_id.assert_not_called()

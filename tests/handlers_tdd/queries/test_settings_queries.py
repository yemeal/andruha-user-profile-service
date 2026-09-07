"""TDD contracts for the read-only settings query handler."""

from datetime import timedelta

import pytest

from app.application.dto.settings import SettingsDTO
from app.application.queries.settings.get_my import GetMySettingsQuery
from app.domain.exceptions import UserSettingsNotFoundError
from app.domain.value_objects.locale import Locale
from app.domain.value_objects.theme import Theme


@pytest.mark.asyncio
async def test_get_my_settings_returns_the_owners_settings(harness) -> None:
    harness.seed_settings(
        theme=Theme.DARK,
        locale=Locale.EN,
        timezone="America/New_York",
    )
    handler = harness.handler("queries/settings/get_my")

    result = await handler(GetMySettingsQuery(user_id=harness.user_id))

    assert isinstance(result, SettingsDTO)
    assert result.user_id == harness.user_id
    assert result.theme is Theme.DARK
    assert result.locale is Locale.EN
    assert result.timezone == "America/New_York"
    assert result.version == 1
    assert result.created_at == harness.now - timedelta(days=1)


@pytest.mark.asyncio
async def test_get_my_settings_raises_when_settings_are_absent(harness) -> None:
    handler = harness.handler("queries/settings/get_my")

    with pytest.raises(UserSettingsNotFoundError):
        await handler(GetMySettingsQuery(user_id=harness.user_id))

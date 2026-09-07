import pytest

from app.application.commands.settings.reset.command import ResetSettingsCommand
from app.application.dto.settings import SettingsDTO
from app.domain.exceptions.user_settings import (
    SettingsVersionMismatchError,
    UserSettingsNotFoundError,
)
from app.domain.value_objects.privacy import PrivacyScope


async def test_reset_restores_preferences_and_privacy_defaults(harness):
    original = harness.seed_settings(
        theme="dark",
        locale="en",
        timezone="UTC",
        privacy={
            "who_can_see_avatar": "NOBODY",
            "who_can_see_bio": "NOBODY",
            "who_can_find_by_username": "NOBODY",
        },
    )
    command = ResetSettingsCommand(user_id=harness.user_id, expected_version=1)
    handler = harness.handler("commands/settings/reset")
    result = await handler(command)
    assert isinstance(result, SettingsDTO)
    assert str(result.theme) == "system" and str(result.locale) == "ru"
    assert result.timezone == "Europe/Moscow"
    assert result.privacy.who_can_see_avatar is PrivacyScope.ALL
    assert result.privacy.who_can_see_bio is PrivacyScope.ALL
    assert result.privacy.who_can_find_by_username is PrivacyScope.ALL
    assert result.version == 2 and result.updated_at == harness.now
    assert result.created_at == original.created_at
    persisted = await harness.settings.get_by_id(harness.user_id)
    assert str(persisted.theme) == "system" and persisted.timezone == "Europe/Moscow"
    assert persisted.privacy == result.privacy and persisted.version == 2


async def test_reset_of_default_settings_is_a_noop(harness):
    original = harness.seed_settings()
    handler = harness.handler("commands/settings/reset")
    result = await handler(
        ResetSettingsCommand(user_id=harness.user_id, expected_version=1)
    )
    assert result.version == 1 and result.updated_at is None
    assert await harness.settings.get_by_id(harness.user_id) == original


async def test_reset_missing_settings_raises_not_found(harness):
    handler = harness.handler("commands/settings/reset")
    with pytest.raises(UserSettingsNotFoundError):
        await handler(ResetSettingsCommand(user_id=harness.user_id, expected_version=1))


async def test_stale_reset_does_not_discard_new_preferences(harness):
    original = harness.seed_settings(theme="dark", version=4)
    handler = harness.handler("commands/settings/reset")
    with pytest.raises(SettingsVersionMismatchError):
        await handler(ResetSettingsCommand(user_id=harness.user_id, expected_version=3))
    assert await harness.settings.get_by_id(harness.user_id) == original

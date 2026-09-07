import pytest

from app.application.commands.settings.update.command import UpdateSettingsCommand
from app.application.dto.settings import SettingsDTO
from app.domain.exceptions.user_settings import (
    InvalidTimezoneError,
    SettingsVersionMismatchError,
    UserSettingsNotFoundError,
)
from app.domain.value_objects.privacy import PrivacyScope


async def test_updates_preferences_and_merges_only_requested_privacy_fields(harness):
    original = harness.seed_settings(
        privacy={
            "who_can_see_avatar": "ALL",
            "who_can_see_bio": "NOBODY",
            "who_can_find_by_username": "NOBODY",
        }
    )
    other = harness.seed_settings(user_id=harness.other_user_id, theme="light")
    command = UpdateSettingsCommand(
        user_id=harness.user_id,
        expected_version=1,
        theme="dark",
        locale="en",
        timezone="UTC",
        who_can_see_avatar="NOBODY",
    )
    handler = harness.handler("commands/settings/update")
    result = await handler(command)
    assert isinstance(result, SettingsDTO)
    assert result.user_id == harness.user_id
    assert str(result.theme) == "dark" and str(result.locale) == "en"
    assert result.timezone == "UTC"
    assert result.privacy.who_can_see_avatar is PrivacyScope.NOBODY
    assert result.privacy.who_can_see_bio is PrivacyScope.NOBODY
    assert result.privacy.who_can_find_by_username is PrivacyScope.NOBODY
    assert result.version == 2 and result.updated_at == harness.now
    assert result.created_at == original.created_at
    persisted = await harness.settings.get_by_id(harness.user_id)
    assert str(persisted.theme) == "dark" and persisted.timezone == "UTC"
    assert persisted.privacy == result.privacy and persisted.version == 2
    assert await harness.settings.get_by_id(harness.other_user_id) == other


@pytest.mark.parametrize("changes", [{}, {"theme": "dark", "timezone": "UTC"}])
async def test_unchanged_settings_preserve_version_and_timestamp(harness, changes):
    original = harness.seed_settings(theme="dark", timezone="UTC", version=4)
    command = UpdateSettingsCommand(
        user_id=harness.user_id, expected_version=4, **changes
    )
    handler = harness.handler("commands/settings/update")
    result = await handler(command)
    assert result.version == 4 and result.updated_at is None
    assert await harness.settings.get_by_id(harness.user_id) == original


async def test_missing_settings_raise_not_found(harness):
    handler = harness.handler("commands/settings/update")
    command = UpdateSettingsCommand(
        user_id=harness.user_id, expected_version=1, theme="dark"
    )
    with pytest.raises(UserSettingsNotFoundError):
        await handler(command)


async def test_stale_settings_update_does_not_overwrite_current_preferences(harness):
    original = harness.seed_settings(theme="light", version=3)
    handler = harness.handler("commands/settings/update")
    command = UpdateSettingsCommand(
        user_id=harness.user_id, expected_version=2, theme="dark"
    )
    with pytest.raises(SettingsVersionMismatchError):
        await handler(command)
    assert await harness.settings.get_by_id(harness.user_id) == original


async def test_invalid_timezone_does_not_persist_other_requested_changes(harness):
    original = harness.seed_settings(theme="light", timezone="UTC")
    command = UpdateSettingsCommand(
        user_id=harness.user_id,
        expected_version=1,
        theme="dark",
        timezone="Mars/Olympus",
    )
    handler = harness.handler("commands/settings/update")
    with pytest.raises(InvalidTimezoneError):
        await handler(command)
    assert await harness.settings.get_by_id(harness.user_id) == original

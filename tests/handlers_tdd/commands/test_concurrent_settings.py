import pytest

from app.application.commands.settings.reset.command import ResetSettingsCommand
from app.application.commands.settings.update.command import UpdateSettingsCommand
from app.domain.aggregates.settings import UserSettings
from app.domain.exceptions.user_settings import SettingsVersionMismatchError


@pytest.mark.parametrize("reset", [False, True])
async def test_concurrent_settings_write_is_not_overwritten(harness, reset):
    original = harness.seed_settings(theme="dark")
    winner = UserSettings.model_validate(
        {
            **original.model_dump(),
            "theme": "light",
            "version": 2,
            "updated_at": harness.now,
        }
    )
    harness.settings.arrange_competing_write(winner)
    command = (
        ResetSettingsCommand(user_id=harness.user_id, expected_version=1)
        if reset
        else UpdateSettingsCommand(
            user_id=harness.user_id, expected_version=1, theme="system"
        )
    )
    handler = harness.handler("commands/settings/" + ("reset" if reset else "update"))
    with pytest.raises(SettingsVersionMismatchError):
        await handler(command)
    assert await harness.settings.get_by_id(harness.user_id) == winner

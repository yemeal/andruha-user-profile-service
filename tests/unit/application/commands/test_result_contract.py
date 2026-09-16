"""Аннотация и фактический результат каждого command handler соответствуют команде."""

from inspect import iscoroutinefunction
from pathlib import Path
from typing import get_type_hints

import pytest

from app.application.commands.base import BaseCommand
from app.application.commands.profiles.create_default.command import (
    CreateDefaultProfileCommand,
)
from app.application.commands.profiles.update.command import UpdateProfileCommand
from app.application.commands.profiles.update_avatar.command import UpdateAvatarCommand
from app.application.commands.settings.reset.command import ResetSettingsCommand
from app.application.commands.settings.update.command import UpdateSettingsCommand

CASES = [
    ("commands/profiles/create_default", CreateDefaultProfileCommand, {}),
    ("commands/profiles/update", UpdateProfileCommand, {"display_name": "Changed"}),
    (
        "commands/profiles/update_avatar",
        UpdateAvatarCommand,
        {"avatar_key": "avatars/new"},
    ),
    ("commands/settings/update", UpdateSettingsCommand, {"theme": "dark"}),
    ("commands/settings/reset", ResetSettingsCommand, {}),
]


def declared_result(command_type):
    # Зависимость от Pydantic generic metadata изолирована в тестах.
    for base in command_type.__mro__:
        metadata = getattr(base, "__pydantic_generic_metadata__", {})
        if metadata.get("origin") is BaseCommand:
            return metadata["args"][0]
    pytest.fail(f"{command_type.__name__} must declare BaseCommand[ResultT]")


@pytest.mark.parametrize(
    "key, command_type, changes", CASES, ids=[case[1].__name__ for case in CASES]
)
@pytest.mark.parametrize("noop", [False, True], ids=["changed", "noop"])
async def test_call_contract_matches_command(harness, key, command_type, changes, noop):
    if command_type is CreateDefaultProfileCommand:
        if noop:
            harness.seed_profile()
            harness.seed_settings()
        command = command_type(user_id=harness.user_id, registered_at=harness.now)
    else:
        harness.seed_profile()
        harness.seed_settings(
            theme="dark"
            if command_type is ResetSettingsCommand and not noop
            else "system"
        )
        command = command_type(
            user_id=harness.user_id, expected_version=1, **({} if noop else changes)
        )

    handler = harness.handler(key)
    expected = declared_result(command_type)
    hints = get_type_hints(type(handler).__call__)
    assert iscoroutinefunction(type(handler).__call__)
    assert hints.get("command") is command_type
    assert hints.get("return") is expected

    result = await handler(command)
    assert isinstance(result, expected), (
        f"{type(handler).__name__} returned {type(result).__name__}; "
        f"{command_type.__name__} requires {expected.__name__}"
    )


def test_contract_cases_cover_every_command():
    commands = Path(__file__).resolve().parents[4] / "src/app/application/commands"
    actual = {
        "commands/" + str(path.parent.relative_to(commands)).replace("\\", "/")
        for path in commands.rglob("command.py")
    }
    assert actual == {case[0] for case in CASES}

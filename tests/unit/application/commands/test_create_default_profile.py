import pytest

from app.application.commands.profiles.create_default.command import (
    CreateDefaultProfileCommand,
)
from app.domain.value_objects.privacy import PrivacyScope
from app.domain.value_objects.status import UserProfileStatus


async def test_creates_a_default_profile_and_settings_for_the_same_user(harness):
    command = CreateDefaultProfileCommand(
        user_id=harness.user_id, registered_at=harness.now
    )
    handler = harness.handler("commands/profiles/create_default")

    assert await handler(command) is None

    profile = await harness.profiles.get_by_id(harness.user_id)
    settings = await harness.settings.get_by_id(harness.user_id)
    assert profile is not None and settings is not None
    assert profile.user_id == settings.user_id == harness.user_id
    assert profile.created_at == settings.created_at == command.registered_at
    assert profile.display_name == "Пользователь"
    assert (
        profile.username is None and profile.bio is None and profile.avatar_key is None
    )
    assert profile.status is UserProfileStatus.ACTIVE and profile.is_verified is False
    assert profile.version == settings.version == 1
    assert str(settings.theme) == "system" and str(settings.locale) == "ru"
    assert settings.timezone == "Europe/Moscow"
    assert settings.privacy.who_can_see_bio is PrivacyScope.ALL
    assert settings.privacy.who_can_see_avatar is PrivacyScope.ALL
    assert settings.privacy.who_can_find_by_username is PrivacyScope.ALL


@pytest.mark.parametrize("existing", ["profile", "settings", "both"])
async def test_initialization_preserves_existing_data_and_fills_missing_half(
    harness, existing
):
    profile = (
        harness.seed_profile(display_name="Existing name", bio="Keep me", version=5)
        if existing in {"profile", "both"}
        else None
    )
    settings = (
        harness.seed_settings(theme="dark", timezone="UTC", version=7)
        if existing in {"settings", "both"}
        else None
    )
    command = CreateDefaultProfileCommand(
        user_id=harness.user_id, registered_at=harness.now
    )
    handler = harness.handler("commands/profiles/create_default")

    await handler(command)
    after_profile = await harness.profiles.get_by_id(harness.user_id)
    after_settings = await harness.settings.get_by_id(harness.user_id)
    assert after_profile is not None and after_settings is not None
    if profile is not None:
        assert after_profile == profile
    else:
        assert after_profile.created_at == command.registered_at
    if settings is not None:
        assert after_settings == settings
    else:
        assert after_settings.created_at == command.registered_at


async def test_repeated_initialization_does_not_reset_profile_or_settings(harness):
    command = CreateDefaultProfileCommand(
        user_id=harness.user_id, registered_at=harness.now
    )
    handler = harness.handler("commands/profiles/create_default")
    await handler(command)
    first_profile = await harness.profiles.get_by_id(harness.user_id)
    first_settings = await harness.settings.get_by_id(harness.user_id)

    assert await handler(command) is None
    assert await harness.profiles.get_by_id(harness.user_id) == first_profile
    assert await harness.settings.get_by_id(harness.user_id) == first_settings

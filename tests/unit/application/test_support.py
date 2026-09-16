"""Check that the test adapters cannot hide missing writes or lost updates."""

import pytest
from tests.unit.application.support import ProfileReader, SettingsReader

from app.domain.exceptions.user_profile import ProfileVersionMismatchError


async def test_repository_returns_detached_aggregates(harness):
    harness.seed_profile(display_name="Original")
    loaded = await harness.profiles.get_by_id(harness.user_id)
    loaded.update_profile(now=harness.now, display_name="Unsaved")
    assert (
        await harness.profiles.get_by_id(harness.user_id)
    ).display_name == "Original"
    await harness.profiles.update(loaded, expected_version=1)
    assert (await harness.profiles.get_by_id(harness.user_id)).display_name == "Unsaved"
    loaded.update_profile(now=harness.now, display_name="Not saved again")
    assert (await harness.profiles.get_by_id(harness.user_id)).display_name == "Unsaved"


async def test_repository_rejects_stale_expected_version(harness):
    original = harness.seed_profile(version=2)
    loaded = await harness.profiles.get_by_id(harness.user_id)
    loaded.update_profile(now=harness.now, display_name="Stale")
    with pytest.raises(ProfileVersionMismatchError):
        await harness.profiles.update(loaded, expected_version=1)
    assert await harness.profiles.get_by_id(harness.user_id) == original


async def test_readers_expose_only_read_ports_and_return_detached_data(harness):
    harness.seed_profile(display_name="Original")
    harness.seed_settings()
    profiles = ProfileReader(harness.profiles)
    settings = SettingsReader(harness.settings)
    assert not hasattr(profiles, "update") and not hasattr(settings, "create")
    loaded = await profiles.get_by_id(harness.user_id)
    loaded.update_profile(now=harness.now, display_name="Unsaved")
    assert (await profiles.get_by_id(harness.user_id)).display_name == "Original"

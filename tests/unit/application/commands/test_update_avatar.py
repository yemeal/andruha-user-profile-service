import pytest

from app.application.commands.profiles.update_avatar.command import UpdateAvatarCommand
from app.application.dto.profiles import ProfileDTO
from app.domain.exceptions.user_profile import (
    ProfileVersionMismatchError,
    UserProfileNotFoundError,
)


@pytest.mark.parametrize("avatar_key", ["avatars/new", None], ids=["replace", "remove"])
async def test_changes_avatar_without_modifying_profile_text(harness, avatar_key):
    harness.seed_profile(
        display_name="Existing", bio="Keep bio", avatar_key="avatars/old"
    )
    command = UpdateAvatarCommand(
        user_id=harness.user_id, expected_version=1, avatar_key=avatar_key
    )
    handler = harness.handler("commands/profiles/update_avatar")
    result = await handler(command)
    assert isinstance(result, ProfileDTO)
    assert result.avatar_key == avatar_key
    assert result.display_name == "Existing" and result.bio == "Keep bio"
    assert result.version == 2 and result.updated_at == harness.now
    persisted = await harness.profiles.get_by_id(harness.user_id)
    assert persisted.avatar_key == avatar_key and persisted.version == 2


async def test_same_avatar_is_a_noop(harness):
    original = harness.seed_profile(avatar_key="avatars/same", version=4)
    command = UpdateAvatarCommand(
        user_id=harness.user_id, expected_version=4, avatar_key="avatars/same"
    )
    handler = harness.handler("commands/profiles/update_avatar")
    result = await handler(command)
    assert result.version == 4 and result.updated_at is None
    assert await harness.profiles.get_by_id(harness.user_id) == original


async def test_missing_profile_cannot_receive_an_avatar(harness):
    handler = harness.handler("commands/profiles/update_avatar")
    command = UpdateAvatarCommand(
        user_id=harness.user_id, expected_version=1, avatar_key="avatars/new"
    )
    with pytest.raises(UserProfileNotFoundError):
        await handler(command)


async def test_stale_avatar_update_preserves_existing_avatar(harness):
    original = harness.seed_profile(avatar_key="avatars/current", version=3)
    handler = harness.handler("commands/profiles/update_avatar")
    command = UpdateAvatarCommand(
        user_id=harness.user_id, expected_version=2, avatar_key=None
    )
    with pytest.raises(ProfileVersionMismatchError):
        await handler(command)
    assert await harness.profiles.get_by_id(harness.user_id) == original

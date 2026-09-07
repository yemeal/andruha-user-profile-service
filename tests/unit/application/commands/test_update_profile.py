import pytest

from app.application.commands.profiles.update.command import UpdateProfileCommand
from app.application.dto.profiles import ProfileDTO
from app.domain.aggregates.profiles import UserProfile
from app.domain.exceptions.user_profile import (
    ProfileVersionMismatchError,
    ReservedUsernameError,
    UsernameAlreadyTakenError,
    UserProfileNotFoundError,
)


async def test_updates_profile_returns_saved_dto_and_preserves_unrelated_fields(
    harness,
):
    original = harness.seed_profile(
        username="alex", bio="Old bio", avatar_key="avatars/original", is_verified=True
    )
    other = harness.seed_profile(
        user_id=harness.other_user_id, display_name="Other user"
    )
    command = UpdateProfileCommand(
        user_id=harness.user_id,
        expected_version=1,
        display_name="  New name  ",
        bio="New bio",
        username="new_name",
    )
    handler = harness.handler("commands/profiles/update")

    result = await handler(command)

    assert isinstance(result, ProfileDTO)
    assert result.user_id == harness.user_id
    assert result.display_name == "New name"
    assert result.bio == "New bio" and result.username == "new_name"
    assert result.version == 2 and result.updated_at == harness.now
    assert result.created_at == original.created_at
    assert result.avatar_key == "avatars/original" and result.is_verified is True
    persisted = await harness.profiles.get_by_id(harness.user_id)
    assert persisted.display_name == "New name" and persisted.version == 2
    assert persisted.bio == "New bio" and persisted.username == "new_name"
    assert await harness.profiles.get_by_id(harness.other_user_id) == other


@pytest.mark.parametrize(
    "changes", [{}, {"display_name": "Existing", "bio": "Keep bio", "username": "alex"}]
)
async def test_no_actual_change_preserves_version_and_timestamp(harness, changes):
    original = harness.seed_profile(
        display_name="Existing", bio="Keep bio", username="alex", version=4
    )
    command = UpdateProfileCommand(
        user_id=harness.user_id, expected_version=4, **changes
    )
    handler = harness.handler("commands/profiles/update")
    result = await handler(command)
    assert result.version == 4 and result.updated_at is None
    assert await harness.profiles.get_by_id(harness.user_id) == original


async def test_empty_bio_clears_it_without_clearing_omitted_username(harness):
    harness.seed_profile(bio="Old bio", username="alex")
    command = UpdateProfileCommand(user_id=harness.user_id, expected_version=1, bio="")
    handler = harness.handler("commands/profiles/update")
    result = await handler(command)
    assert result.bio is None and result.username == "alex"
    persisted = await harness.profiles.get_by_id(harness.user_id)
    assert persisted.bio is None and persisted.username == "alex"


async def test_missing_profile_raises_not_found(harness):
    handler = harness.handler("commands/profiles/update")
    command = UpdateProfileCommand(
        user_id=harness.user_id, expected_version=1, display_name="New"
    )
    with pytest.raises(UserProfileNotFoundError):
        await handler(command)
    assert not await harness.profiles.exists(harness.user_id)


async def test_stale_version_cannot_overwrite_profile(harness):
    original = harness.seed_profile(display_name="Existing", version=4)
    handler = harness.handler("commands/profiles/update")
    command = UpdateProfileCommand(
        user_id=harness.user_id, expected_version=3, display_name="Stale edit"
    )
    with pytest.raises(ProfileVersionMismatchError):
        await handler(command)
    assert await harness.profiles.get_by_id(harness.user_id) == original


async def test_username_collision_does_not_persist_partial_profile_changes(harness):
    original = harness.seed_profile(display_name="Original", username="alex")
    owner = harness.seed_profile(user_id=harness.other_user_id, username="taken")
    handler = harness.handler("commands/profiles/update")
    command = UpdateProfileCommand(
        user_id=harness.user_id,
        expected_version=1,
        display_name="Must not persist",
        username="taken",
    )
    with pytest.raises(UsernameAlreadyTakenError):
        await handler(command)
    assert await harness.profiles.get_by_id(harness.user_id) == original
    assert await harness.profiles.get_by_id(harness.other_user_id) == owner


async def test_domain_validation_failure_does_not_persist_earlier_fields(harness):
    original = harness.seed_profile(display_name="Original", username="alex")
    command = UpdateProfileCommand(
        user_id=harness.user_id,
        expected_version=1,
        display_name="Must not persist",
        username="admin",
    )
    handler = harness.handler("commands/profiles/update")
    with pytest.raises(ReservedUsernameError):
        await handler(command)
    assert await harness.profiles.get_by_id(harness.user_id) == original


async def test_competing_commit_between_load_and_save_is_not_overwritten(harness):
    original = harness.seed_profile(display_name="Original")
    competing = UserProfile.model_validate(
        {
            **original.model_dump(),
            "display_name": "Concurrent winner",
            "version": 2,
            "updated_at": harness.now,
        }
    )
    harness.profiles.arrange_competing_write(competing)
    command = UpdateProfileCommand(
        user_id=harness.user_id, expected_version=1, display_name="Losing edit"
    )
    handler = harness.handler("commands/profiles/update")
    with pytest.raises(ProfileVersionMismatchError):
        await handler(command)
    assert await harness.profiles.get_by_id(harness.user_id) == competing

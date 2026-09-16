"""TDD contracts for the read-only profile query handlers.

The handler modules deliberately do not exist yet.  ``harness.handler`` loads
them from each test body, so collection stays useful while implementation is
still in the red phase.
"""

from datetime import timedelta

import pytest

from app.application.dto.profiles import ProfileDTO, PublicProfileDTO
from app.application.queries.profiles.check_exists import CheckProfileExistsQuery
from app.application.queries.profiles.get_batch import GetBatchProfilesQuery
from app.application.queries.profiles.get_my import GetMyProfileQuery
from app.application.queries.profiles.get_public import GetPublicProfileQuery
from app.application.queries.profiles.search_by_username import (
    SearchByUsernameQuery,
)
from app.domain.exceptions import UserProfileNotFoundError
from app.domain.value_objects.privacy import PrivacyScope, PrivacySettings


@pytest.mark.asyncio
async def test_get_my_profile_returns_the_owners_complete_profile(harness) -> None:
    harness.seed_profile(
        username="owner_name",
        display_name="Owner Name",
        bio="Private biography",
        avatar_key="avatars/owner.png",
        is_verified=True,
    )
    handler = harness.handler("queries/profiles/get_my")

    result = await handler(GetMyProfileQuery(user_id=harness.user_id))

    assert isinstance(result, ProfileDTO)
    assert result.user_id == harness.user_id
    assert result.username == "owner_name"
    assert result.display_name == "Owner Name"
    assert result.bio == "Private biography"
    assert result.avatar_key == "avatars/owner.png"
    assert result.is_verified is True
    assert result.version == 1
    assert result.created_at == harness.now - timedelta(days=1)


@pytest.mark.asyncio
async def test_get_my_profile_raises_when_profile_is_absent(harness) -> None:
    handler = harness.handler("queries/profiles/get_my")

    with pytest.raises(UserProfileNotFoundError):
        await handler(GetMyProfileQuery(user_id=harness.user_id))


@pytest.mark.asyncio
async def test_get_public_profile_returns_only_public_projection(harness) -> None:
    harness.seed_profile(
        user_id=harness.other_user_id,
        username="public_owner",
        display_name="Public Owner",
        bio="Visible bio",
        avatar_key="avatars/public.png",
        is_verified=True,
    )
    harness.seed_settings(user_id=harness.other_user_id)
    handler = harness.handler("queries/profiles/get_public")

    result = await handler(
        GetPublicProfileQuery(
            user_id=harness.other_user_id,
            viewer_id=harness.user_id,
        )
    )

    assert isinstance(result, PublicProfileDTO)
    assert result.user_id == harness.other_user_id
    assert result.username == "public_owner"
    assert result.display_name == "Public Owner"
    assert result.bio == "Visible bio"
    assert result.avatar_key == "avatars/public.png"
    assert result.is_verified is True
    assert not hasattr(result, "status")
    assert not hasattr(result, "version")


@pytest.mark.asyncio
async def test_get_public_profile_masks_sensitive_fields_for_external_viewer(
    harness,
) -> None:
    harness.seed_profile(
        user_id=harness.other_user_id,
        username="private_owner",
        bio="Hidden bio",
        avatar_key="avatars/private.png",
    )
    harness.seed_settings(
        user_id=harness.other_user_id,
        privacy=PrivacySettings(
            who_can_see_avatar=PrivacyScope.NOBODY,
            who_can_see_bio=PrivacyScope.NOBODY,
        ),
    )
    handler = harness.handler("queries/profiles/get_public")

    result = await handler(
        GetPublicProfileQuery(
            user_id=harness.other_user_id,
            viewer_id=harness.user_id,
        )
    )

    assert result.bio is None
    assert result.avatar_key is None


@pytest.mark.asyncio
async def test_get_public_profile_raises_when_profile_is_absent(harness) -> None:
    handler = harness.handler("queries/profiles/get_public")

    with pytest.raises(UserProfileNotFoundError):
        await handler(GetPublicProfileQuery(user_id=harness.other_user_id))


@pytest.mark.asyncio
async def test_search_by_username_returns_public_profile_for_visible_username(
    harness,
) -> None:
    harness.seed_profile(
        user_id=harness.other_user_id,
        username="case_sensitive",
        display_name="Search Result",
    )
    harness.seed_settings(user_id=harness.other_user_id)
    handler = harness.handler("queries/profiles/search_by_username")

    result = await handler(
        SearchByUsernameQuery(username="CASE_SENSITIVE", viewer_id=harness.user_id)
    )

    assert isinstance(result, PublicProfileDTO)
    assert result.user_id == harness.other_user_id
    assert result.username == "case_sensitive"
    assert result.display_name == "Search Result"


@pytest.mark.asyncio
async def test_search_by_username_raises_when_profile_is_absent(harness) -> None:
    handler = harness.handler("queries/profiles/search_by_username")

    with pytest.raises(UserProfileNotFoundError):
        await handler(SearchByUsernameQuery(username="unknown_user"))


@pytest.mark.asyncio
async def test_search_by_username_does_not_disclose_a_private_username_to_external_viewer(
    harness,
) -> None:
    harness.seed_profile(
        user_id=harness.other_user_id,
        username="private_search",
        display_name="Private Search",
    )
    harness.seed_settings(
        user_id=harness.other_user_id,
        privacy=PrivacySettings(who_can_find_by_username=PrivacyScope.NOBODY),
    )
    handler = harness.handler("queries/profiles/search_by_username")

    try:
        result = await handler(
            SearchByUsernameQuery(username="private_search", viewer_id=harness.user_id)
        )
    except UserProfileNotFoundError:
        return

    assert result is None


@pytest.mark.asyncio
async def test_search_by_username_allows_owner_to_find_private_username(
    harness,
) -> None:
    harness.seed_profile(username="private_self", bio="Owner-only bio")
    harness.seed_settings(
        privacy=PrivacySettings(who_can_find_by_username=PrivacyScope.NOBODY),
    )
    handler = harness.handler("queries/profiles/search_by_username")

    result = await handler(
        SearchByUsernameQuery(username="private_self", viewer_id=harness.user_id)
    )

    assert result is not None
    assert result.user_id == harness.user_id
    assert result.username == "private_self"


@pytest.mark.asyncio
async def test_get_batch_profiles_returns_public_dtos_for_requested_profiles(
    harness,
) -> None:
    harness.seed_profile(
        user_id=harness.user_id,
        username="first_profile",
        display_name="First",
    )
    harness.seed_settings(user_id=harness.user_id)
    harness.seed_profile(
        user_id=harness.other_user_id,
        username="second_profile",
        display_name="Second",
    )
    harness.seed_settings(user_id=harness.other_user_id)
    handler = harness.handler("queries/profiles/get_batch")

    result = await handler(
        GetBatchProfilesQuery(
            user_ids=[harness.other_user_id, harness.user_id],
            viewer_id=harness.user_id,
        )
    )

    assert len(result) == 2
    assert all(isinstance(profile, PublicProfileDTO) for profile in result)
    by_id = {profile.user_id: profile for profile in result}
    assert set(by_id) == {harness.user_id, harness.other_user_id}
    assert by_id[harness.user_id].display_name == "First"
    assert by_id[harness.other_user_id].display_name == "Second"


@pytest.mark.asyncio
async def test_get_batch_profiles_applies_privacy_to_each_public_projection(
    harness,
) -> None:
    harness.seed_profile(
        user_id=harness.other_user_id,
        username="hidden_batch",
        bio="Hidden bio",
        avatar_key="avatars/hidden.png",
    )
    harness.seed_settings(
        user_id=harness.other_user_id,
        privacy=PrivacySettings(
            who_can_see_avatar=PrivacyScope.NOBODY,
            who_can_see_bio=PrivacyScope.NOBODY,
        ),
    )
    handler = harness.handler("queries/profiles/get_batch")

    result = await handler(
        GetBatchProfilesQuery(
            user_ids=[harness.other_user_id],
            viewer_id=harness.user_id,
        )
    )

    assert len(result) == 1
    assert result[0].user_id == harness.other_user_id
    assert result[0].bio is None
    assert result[0].avatar_key is None


@pytest.mark.asyncio
async def test_check_profile_exists_reports_existing_and_absent_profiles(
    harness,
) -> None:
    harness.seed_profile(user_id=harness.user_id)
    handler = harness.handler("queries/profiles/check_exists")

    existing = await handler(CheckProfileExistsQuery(user_id=harness.user_id))
    absent = await handler(CheckProfileExistsQuery(user_id=harness.other_user_id))

    assert existing is True
    assert absent is False

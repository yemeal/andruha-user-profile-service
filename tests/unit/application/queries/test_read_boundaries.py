from uuid import uuid4

import pytest

from app.application.queries.profiles.get_batch.query import GetBatchProfilesQuery
from app.application.queries.profiles.get_public.query import GetPublicProfileQuery
from app.application.queries.profiles.search_by_username.query import (
    SearchByUsernameQuery,
)
from app.domain.exceptions.user_profile import UserProfileNotFoundError
from app.domain.exceptions.user_settings import UserSettingsNotFoundError


@pytest.mark.parametrize("kind", ["get_public", "search_by_username", "get_batch"])
async def test_missing_settings_never_fall_back_to_public_defaults(harness, kind):
    harness.seed_profile(
        username="private_user", bio="Secret", avatar_key="private/avatar"
    )
    query = {
        "get_public": GetPublicProfileQuery(user_id=harness.user_id),
        "search_by_username": SearchByUsernameQuery(username="private_user"),
        "get_batch": GetBatchProfilesQuery(user_ids=[harness.user_id]),
    }[kind]
    with pytest.raises(UserSettingsNotFoundError):
        await harness.handler("queries/profiles/" + kind)(query)
    assert await harness.settings.get_by_id(harness.user_id) is None


async def test_batch_preserves_request_order_and_omits_missing_profiles(harness):
    harness.seed_profile()
    harness.seed_settings()
    harness.seed_profile(user_id=harness.other_user_id)
    harness.seed_settings(user_id=harness.other_user_id)
    result = await harness.handler("queries/profiles/get_batch")(
        GetBatchProfilesQuery(
            user_ids=[
                harness.other_user_id,
                uuid4(),
                harness.user_id,
                harness.other_user_id,
            ]
        )
    )
    assert [profile.user_id for profile in result] == [
        harness.other_user_id,
        harness.user_id,
    ]


@pytest.mark.parametrize("owner", [False, True])
async def test_public_privacy_for_owner_and_anonymous_viewer(harness, owner):
    harness.seed_profile(bio="Private", avatar_key="private/avatar")
    harness.seed_settings(
        privacy={"who_can_see_bio": "NOBODY", "who_can_see_avatar": "NOBODY"}
    )
    result = await harness.handler("queries/profiles/get_public")(
        GetPublicProfileQuery(
            user_id=harness.user_id, viewer_id=harness.user_id if owner else None
        )
    )
    assert result.bio == ("Private" if owner else None)
    assert result.avatar_key == ("private/avatar" if owner else None)


async def test_private_username_raises_same_error_as_missing_username(harness):
    harness.seed_profile(username="hidden_user")
    harness.seed_settings(privacy={"who_can_find_by_username": "NOBODY"})
    handler = harness.handler("queries/profiles/search_by_username")
    for username in ("hidden_user", "missing_user"):
        with pytest.raises(UserProfileNotFoundError):
            await handler(SearchByUsernameQuery(username=username))

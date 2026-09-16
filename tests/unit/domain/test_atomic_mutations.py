from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.aggregates.profiles import UserProfile
from app.domain.aggregates.settings import UserSettings
from app.domain.exceptions.base import InvalidTimestampError
from app.domain.exceptions.user_profile import ReservedUsernameError
from app.domain.exceptions.user_settings import InvalidTimezoneError

NOW = datetime(2026, 9, 7, tzinfo=UTC)


@pytest.mark.parametrize("aggregate_type", [UserProfile, UserSettings])
def test_fields_cannot_be_assigned_or_deleted_directly(aggregate_type):
    aggregate = aggregate_type.create_default(uuid4(), NOW)
    before = aggregate.model_dump()
    for name in aggregate_type.model_fields:
        with pytest.raises(ValidationError):
            setattr(aggregate, name, getattr(aggregate, name))
        with pytest.raises(ValidationError):
            delattr(aggregate, name)
    assert aggregate.model_dump() == before


def test_invalid_username_leaves_entire_profile_unchanged():
    profile = UserProfile.create_default(uuid4(), NOW)
    before = profile.model_dump()
    with pytest.raises(ReservedUsernameError):
        profile.update_profile(
            display_name="Changed",
            bio="Changed bio",
            username="admin",
            now=NOW + timedelta(seconds=1),
        )
    assert profile.model_dump() == before


def test_invalid_timezone_leaves_entire_settings_unchanged():
    settings = UserSettings.create_default(uuid4(), NOW)
    before = settings.model_dump()
    with pytest.raises(InvalidTimezoneError):
        settings.update_settings(
            theme="dark",
            locale="en",
            timezone="Missing/Timezone",
            now=NOW + timedelta(seconds=1),
        )
    assert settings.model_dump() == before


@pytest.mark.parametrize(
    "method, kwargs",
    [
        ("update_profile", {"display_name": "Changed"}),
        ("update_avatar", {"avatar_key": "avatars/new"}),
        ("deactivate", {}),
        ("block", {}),
        ("activate", {}),
        ("verify", {}),
        ("unverify", {}),
    ],
)
def test_invalid_time_leaves_profile_transition_unchanged(method, kwargs):
    profile = UserProfile.create_default(uuid4(), NOW)
    if method == "activate":
        profile.block(NOW + timedelta(seconds=1))
    if method == "unverify":
        profile.verify(NOW + timedelta(seconds=1))
    before = profile.model_dump()
    with pytest.raises(InvalidTimestampError):
        getattr(profile, method)(now=NOW, **kwargs)
    assert profile.model_dump() == before


@pytest.mark.parametrize("reset", [False, True])
def test_invalid_time_leaves_settings_unchanged(reset):
    settings = UserSettings.create_default(uuid4(), NOW)
    if reset:
        settings.update_settings(theme="dark", now=NOW + timedelta(seconds=1))
    before = settings.model_dump()
    with pytest.raises(InvalidTimestampError):
        if reset:
            settings.reset_to_defaults(NOW)
        else:
            settings.update_settings(theme="dark", now=NOW)
    assert settings.model_dump() == before


def test_normalized_noop_does_not_increment_version():
    profile = UserProfile.create_default(uuid4(), NOW)
    profile.update_profile(username="alex", now=NOW + timedelta(seconds=1))
    before = profile.model_dump()
    assert not profile.update_profile(
        display_name="  Пользователь  ",
        username="ALEX",
        now=NOW + timedelta(seconds=2),
    )
    assert profile.model_dump() == before

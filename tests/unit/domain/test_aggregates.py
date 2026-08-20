"""Unit tests for UserProfile and UserSettings domain aggregates."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.aggregates import UserProfile, UserProfileStatus, UserSettings
from app.domain.exceptions import (
    InvalidBioError,
    InvalidDisplayNameError,
    InvalidTimestampError,
    InvalidVersionError,
    ReservedUsernameError,
)
from app.domain.value_objects.display_name import DEFAULT_DISPLAY_NAME
from app.domain.value_objects.locale import Locale
from app.domain.value_objects.privacy import PrivacyScope, PrivacySettings
from app.domain.value_objects.theme import Theme
from app.domain.value_objects.timezone import DEFAULT_TIMEZONE
from app.domain.value_objects.username import Username


class TestUserProfileAggregate:
    """Tests for UserProfile Aggregate Root."""

    def test_create_default_profile(self) -> None:
        user_id = uuid.uuid4()
        now = datetime.now(UTC)

        profile = UserProfile.create_default(user_id=user_id, now=now)

        assert profile.user_id == user_id
        assert profile.username is None
        assert profile.display_name == DEFAULT_DISPLAY_NAME
        assert profile.bio is None
        assert profile.avatar_key is None
        assert profile.status == UserProfileStatus.ACTIVE
        assert profile.is_active is True
        assert profile.is_blocked is False
        assert profile.is_verified is False
        assert profile.version == 1
        assert profile.created_at == now
        assert profile.updated_at is None

    def test_update_profile_fields(self) -> None:
        user_id = uuid.uuid4()
        t0 = datetime.now(UTC)
        profile = UserProfile.create_default(user_id=user_id, now=t0)

        t1 = t0 + timedelta(minutes=5)
        changed = profile.update_profile(
            now=t1,
            display_name="Алексей Смирнов",
            bio="Backend developer",
            username="alex_smirnov",
        )

        assert changed is True
        assert profile.display_name == "Алексей Смирнов"
        assert profile.bio == "Backend developer"
        assert profile.username == Username("alex_smirnov")
        assert profile.updated_at == t1
        assert profile.version == 2

    def test_update_profile_partial_fields(self) -> None:
        user_id = uuid.uuid4()
        t0 = datetime.now(UTC)
        profile = UserProfile.create_default(user_id=user_id, now=t0)

        t1 = t0 + timedelta(minutes=5)
        # Update only bio
        changed = profile.update_profile(
            now=t1, display_name=None, bio="Just updated my bio", username=None
        )

        assert changed is True
        assert profile.display_name == "Пользователь"  # unchanged
        assert profile.bio == "Just updated my bio"
        assert profile.updated_at == t1
        assert profile.version == 2

    def test_update_profile_noop_returns_false(self) -> None:
        user_id = uuid.uuid4()
        t0 = datetime.now(UTC)
        profile = UserProfile.create_default(user_id=user_id, now=t0)

        t1 = t0 + timedelta(minutes=5)
        # Passing identical values
        changed = profile.update_profile(
            now=t1, display_name="Пользователь", bio=None, username=None
        )

        assert changed is False
        assert profile.updated_at is None  # unchanged
        assert profile.version == 1

    def test_update_profile_with_invalid_display_name_fails(self) -> None:
        user_id = uuid.uuid4()
        profile = UserProfile.create_default(user_id=user_id, now=datetime.now(UTC))

        with pytest.raises(InvalidDisplayNameError):
            profile.update_profile(
                now=datetime.now(UTC) + timedelta(minutes=1),
                display_name="Alex 😊",
                bio=None,
                username=None,
            )

    def test_update_profile_with_reserved_username_fails(self) -> None:
        user_id = uuid.uuid4()
        profile = UserProfile.create_default(user_id=user_id, now=datetime.now(UTC))

        with pytest.raises(ReservedUsernameError):
            profile.update_profile(
                now=datetime.now(UTC) + timedelta(minutes=1),
                display_name=None,
                bio=None,
                username="admin",
            )

    def test_update_profile_with_invalid_bio_fails(self) -> None:
        user_id = uuid.uuid4()
        profile = UserProfile.create_default(user_id=user_id, now=datetime.now(UTC))

        with pytest.raises(InvalidBioError):
            profile.update_profile(
                now=datetime.now(UTC) + timedelta(minutes=1),
                display_name=None,
                bio="Multi\nline",
                username=None,
            )

    def test_lifecycle_status_transitions(self) -> None:
        user_id = uuid.uuid4()
        t0 = datetime.now(UTC)
        profile = UserProfile.create_default(user_id=user_id, now=t0)

        assert profile.is_active is True
        assert profile.is_blocked is False
        assert profile.version == 1

        # 1. Deactivate
        t1 = t0 + timedelta(minutes=1)
        profile.deactivate(now=t1)
        assert profile.status == UserProfileStatus.DISABLED
        assert profile.is_active is False
        assert profile.is_blocked is False
        assert profile.updated_at == t1
        assert profile.version == 2

        # Idempotent deactivate (no-op timestamp and version)
        t2 = t1 + timedelta(minutes=1)
        profile.deactivate(now=t2)
        assert profile.updated_at == t1
        assert profile.version == 2

        # 2. Block
        t3 = t2 + timedelta(minutes=1)
        profile.block(now=t3)
        assert profile.status == UserProfileStatus.BLOCKED
        assert profile.is_active is False
        assert profile.is_blocked is True
        assert profile.updated_at == t3
        assert profile.version == 3

        # Idempotent block
        t4 = t3 + timedelta(minutes=1)
        profile.block(now=t4)
        assert profile.updated_at == t3
        assert profile.version == 3

        # 3. Activate
        t5 = t4 + timedelta(minutes=1)
        profile.activate(now=t5)
        assert profile.status == UserProfileStatus.ACTIVE
        assert profile.is_active is True
        assert profile.is_blocked is False
        assert profile.updated_at == t5
        assert profile.version == 4

    def test_update_avatar(self) -> None:
        user_id = uuid.uuid4()
        t0 = datetime.now(UTC)
        profile = UserProfile.create_default(user_id=user_id, now=t0)

        # 1. Set avatar key
        t1 = t0 + timedelta(minutes=1)
        changed = profile.update_avatar("avatars/user_123/avatar.webp", now=t1)
        assert changed is True
        assert profile.avatar_key == "avatars/user_123/avatar.webp"
        assert profile.updated_at == t1
        assert profile.version == 2

        # 2. Noop when passing identical key
        t2 = t1 + timedelta(minutes=1)
        changed = profile.update_avatar("avatars/user_123/avatar.webp", now=t2)
        assert changed is False
        assert profile.updated_at == t1
        assert profile.version == 2

        # 3. Remove avatar (set to None)
        t3 = t2 + timedelta(minutes=1)
        changed = profile.update_avatar(None, now=t3)
        assert changed is True
        assert profile.avatar_key is None
        assert profile.updated_at == t3
        assert profile.version == 3

    def test_verify_and_unverify(self) -> None:
        user_id = uuid.uuid4()
        t0 = datetime.now(UTC)
        profile = UserProfile.create_default(user_id=user_id, now=t0)

        assert profile.is_verified is False
        assert profile.version == 1

        # 1. Verify
        t1 = t0 + timedelta(minutes=1)
        profile.verify(now=t1)
        assert profile.is_verified is True
        assert profile.updated_at == t1
        assert profile.version == 2

        # Idempotent verify
        t2 = t1 + timedelta(minutes=1)
        profile.verify(now=t2)
        assert profile.updated_at == t1
        assert profile.version == 2

        # 2. Unverify
        t3 = t2 + timedelta(minutes=1)
        profile.unverify(now=t3)
        assert profile.is_verified is False
        assert profile.updated_at == t3
        assert profile.version == 3

        # Idempotent unverify
        t4 = t3 + timedelta(minutes=1)
        profile.unverify(now=t4)
        assert profile.updated_at == t3
        assert profile.version == 3

    @pytest.mark.parametrize("invalid_version", [0, -1, -100])
    def test_version_cannot_be_zero_or_negative(self, invalid_version: int) -> None:
        with pytest.raises(InvalidVersionError):
            UserProfile(
                user_id=uuid.uuid4(),
                version=invalid_version,
            )

    def test_updated_at_must_be_strictly_greater_than_created_at(self) -> None:
        t0 = datetime.now(UTC)
        t_before = t0 - timedelta(seconds=1)

        # 1. updated_at earlier than created_at -> raises error
        with pytest.raises(InvalidTimestampError):
            UserProfile(
                user_id=uuid.uuid4(),
                created_at=t0,
                updated_at=t_before,
            )

        # 2. updated_at equal to created_at -> raises error (must be strictly greater)
        with pytest.raises(InvalidTimestampError):
            UserProfile(
                user_id=uuid.uuid4(),
                created_at=t0,
                updated_at=t0,
            )


class TestUserSettingsAggregate:
    """Tests for UserSettings Aggregate Root."""

    def test_create_default_settings(self) -> None:
        user_id = uuid.uuid4()
        now = datetime.now(UTC)

        settings = UserSettings.create_default(user_id=user_id, now=now)

        assert settings.user_id == user_id
        assert settings.theme == Theme.SYSTEM
        assert settings.locale == Locale.RU
        assert settings.timezone == DEFAULT_TIMEZONE
        assert settings.privacy == PrivacySettings.default()
        assert settings.version == 1
        assert settings.created_at == now
        assert settings.updated_at is None

    def test_update_settings_fields(self) -> None:
        user_id = uuid.uuid4()
        t0 = datetime.now(UTC)
        settings = UserSettings.create_default(user_id=user_id, now=t0)

        t1 = t0 + timedelta(minutes=5)
        new_privacy = PrivacySettings(
            who_can_see_avatar=PrivacyScope.NOBODY,
            who_can_find_by_username=PrivacyScope.ALL,
            who_can_see_bio=PrivacyScope.NOBODY,
        )

        changed = settings.update_settings(
            theme=Theme.DARK,
            locale=Locale.EN,
            timezone="UTC",
            privacy=new_privacy,
            now=t1,
        )

        assert changed is True
        assert settings.theme == Theme.DARK
        assert settings.locale == Locale.EN
        assert settings.timezone == "UTC"
        assert settings.privacy == new_privacy
        assert settings.updated_at == t1
        assert settings.version == 2

    def test_update_settings_noop_returns_false(self) -> None:
        user_id = uuid.uuid4()
        t0 = datetime.now(UTC)
        settings = UserSettings.create_default(user_id=user_id, now=t0)

        t1 = t0 + timedelta(minutes=5)
        changed = settings.update_settings(
            theme=Theme.SYSTEM,
            locale=Locale.RU,
            timezone="Europe/Moscow",
            privacy=PrivacySettings.default(),
            now=t1,
        )

        assert changed is False
        assert settings.updated_at is None
        assert settings.version == 1

    def test_reset_to_defaults(self) -> None:
        user_id = uuid.uuid4()
        t0 = datetime.now(UTC)
        settings = UserSettings.create_default(user_id=user_id, now=t0)

        # 1. Reset on already-default settings is no-op
        t1 = t0 + timedelta(minutes=1)
        changed = settings.reset_to_defaults(now=t1)
        assert changed is False
        assert settings.updated_at is None
        assert settings.version == 1

        # 2. Modify settings
        t2 = t1 + timedelta(minutes=1)
        custom_privacy = PrivacySettings(
            who_can_see_avatar=PrivacyScope.NOBODY,
            who_can_find_by_username=PrivacyScope.NOBODY,
            who_can_see_bio=PrivacyScope.NOBODY,
        )
        settings.update_settings(
            theme=Theme.DARK,
            locale=Locale.EN,
            timezone="Asia/Tokyo",
            privacy=custom_privacy,
            now=t2,
        )
        assert settings.theme == Theme.DARK
        assert settings.locale == Locale.EN
        assert settings.timezone == "Asia/Tokyo"
        assert settings.privacy == custom_privacy
        assert settings.updated_at == t2
        assert settings.version == 2

        # 3. Reset to defaults
        t3 = t2 + timedelta(minutes=1)
        changed = settings.reset_to_defaults(now=t3)
        assert changed is True
        assert settings.theme == Theme.SYSTEM
        assert settings.locale == Locale.RU
        assert settings.timezone == DEFAULT_TIMEZONE
        assert settings.privacy == PrivacySettings.default()
        assert settings.updated_at == t3
        assert settings.version == 3

    @pytest.mark.parametrize("invalid_version", [0, -1])
    def test_settings_version_cannot_be_zero_or_negative(
        self, invalid_version: int
    ) -> None:
        with pytest.raises(InvalidVersionError):
            UserSettings(
                user_id=uuid.uuid4(),
                version=invalid_version,
            )

    def test_settings_updated_at_must_be_strictly_greater_than_created_at(self) -> None:
        t0 = datetime.now(UTC)
        t_before = t0 - timedelta(seconds=1)

        with pytest.raises(InvalidTimestampError):
            UserSettings(
                user_id=uuid.uuid4(),
                created_at=t0,
                updated_at=t_before,
            )

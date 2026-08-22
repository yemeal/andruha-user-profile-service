"""Unit tests for User Profile Service domain value objects."""

import pytest
from pydantic import TypeAdapter

from app.domain.exceptions import (
    InvalidBioError,
    InvalidDisplayNameError,
    InvalidLocaleError,
    InvalidPrivacyScopeError,
    InvalidProfileStatusError,
    InvalidThemeError,
    InvalidTimezoneError,
    InvalidUsernameError,
    ReservedUsernameError,
)
from app.domain.value_objects.bio import Bio
from app.domain.value_objects.display_name import DEFAULT_DISPLAY_NAME, DisplayName
from app.domain.value_objects.locale import Locale
from app.domain.value_objects.privacy import PrivacyScope, PrivacySettings
from app.domain.value_objects.status import UserProfileStatus
from app.domain.value_objects.theme import Theme
from app.domain.value_objects.timezone import DEFAULT_TIMEZONE, Timezone
from app.domain.value_objects.username import Username


class TestUsernameValueObject:
    """Tests for the Username standalone class value object."""

    @pytest.mark.parametrize(
        "valid_username",
        [
            "alex",
            "john_doe",
            "user123",
            "a_b_c_3",
            "andruha_user",
            "abc",  # min length: 3
            "a" * 32,  # max length: 32
        ],
    )
    def test_valid_usernames_accepted(self, valid_username: str) -> None:
        username = Username(valid_username)
        assert str(username) == valid_username.lower()

    def test_username_is_strictly_lowercase_or_normalized(self) -> None:
        username = Username("Alex_Doe")
        assert str(username) == "alex_doe"

    @pytest.mark.parametrize(
        "invalid_username",
        [
            "ab",  # too short (< 3)
            "a" * 33,  # too long (> 32)
            "alex-doe",  # hyphen not allowed
            "alex.doe",  # dot not allowed
            "alex doe",  # spaces not allowed
            "alex@doe",  # special characters not allowed
            "алекс",  # cyrillic not allowed (latin only)
            "user!",
            "",
        ],
    )
    def test_invalid_username_format_raises_error(self, invalid_username: str) -> None:
        with pytest.raises(InvalidUsernameError):
            Username(invalid_username)

    @pytest.mark.parametrize(
        "reserved_name",
        [
            "admin",
            "administrator",
            "root",
            "system",
            "support",
            "help",
            "api",
            "bot",
            "official",
            "andruha",
            "moderator",
            "service",
            "null",
            "undefined",
        ],
    )
    def test_reserved_usernames_raise_error(self, reserved_name: str) -> None:
        with pytest.raises(ReservedUsernameError):
            Username(reserved_name)


class TestDisplayNameValueObject:
    """Tests for DisplayName (Annotated with AfterValidator)."""

    adapter = TypeAdapter(DisplayName)

    @pytest.mark.parametrize(
        ("raw_name", "expected_clean"),
        [
            ("Алексей", "Алексей"),
            ("John Doe", "John Doe"),
            ("  Alex  ", "Alex"),  # auto-trimming
            ("Пользователь #1", "Пользователь #1"),
            ("A", "A"),  # min length: 1
            ("A" * 64, "A" * 64),  # max length: 64
        ],
    )
    def test_valid_display_names(self, raw_name: str, expected_clean: str) -> None:
        display_name = self.adapter.validate_python(raw_name)
        assert display_name == expected_clean

    def test_default_display_name_is_user(self) -> None:
        assert DEFAULT_DISPLAY_NAME == "Пользователь"

    @pytest.mark.parametrize(
        "invalid_name",
        [
            "",  # empty
            "   ",  # whitespace only
            "A" * 65,  # too long (> 64)
        ],
    )
    def test_invalid_length_display_name_raises_error(self, invalid_name: str) -> None:
        with pytest.raises(InvalidDisplayNameError):
            self.adapter.validate_python(invalid_name)

    @pytest.mark.parametrize(
        "emoji_name",
        [
            "Alex 😊",
            "John 🚀",
            "🔥",
            "User 👾 123",
        ],
    )
    def test_display_name_with_emojis_raises_error(self, emoji_name: str) -> None:
        with pytest.raises(InvalidDisplayNameError):
            self.adapter.validate_python(emoji_name)


class TestBioValueObject:
    """Tests for Bio (Annotated with AfterValidator)."""

    adapter = TypeAdapter(Bio)

    def test_valid_bio(self) -> None:
        bio_text = "Software engineer building distributed systems."
        bio = self.adapter.validate_python(bio_text)
        assert bio == bio_text

    def test_bio_max_length_255(self) -> None:
        valid_bio_text = "A" * 255
        bio = self.adapter.validate_python(valid_bio_text)
        assert len(bio) == 255

        with pytest.raises(InvalidBioError):
            self.adapter.validate_python("A" * 256)

    @pytest.mark.parametrize(
        "multiline_bio",
        [
            "First line\nSecond line",
            "Hello\r\nWorld",
            "Line\rAnother",
        ],
    )
    def test_bio_with_newlines_raises_error(self, multiline_bio: str) -> None:
        with pytest.raises(InvalidBioError):
            self.adapter.validate_python(multiline_bio)


class TestThemeValueObject:
    """Tests for the Theme enum."""

    def test_theme_values(self) -> None:
        assert Theme.SYSTEM == "system"
        assert Theme.LIGHT == "light"
        assert Theme.DARK == "dark"

    def test_theme_default(self) -> None:
        assert Theme.default() == Theme.SYSTEM

    def test_invalid_theme_raises_error(self) -> None:
        with pytest.raises(InvalidThemeError):
            Theme("neon")


class TestLocaleValueObject:
    """Tests for the Locale enum."""

    def test_locale_values(self) -> None:
        assert Locale.RU == "ru"
        assert Locale.EN == "en"
        assert Locale.default() == Locale.RU

    def test_invalid_locale_raises_error(self) -> None:
        with pytest.raises(InvalidLocaleError):
            Locale("fr")


class TestTimezoneValueObject:
    """Tests for Timezone (Annotated with AfterValidator)."""

    adapter = TypeAdapter(Timezone)

    def test_valid_timezones(self) -> None:
        assert self.adapter.validate_python("Europe/Moscow") == "Europe/Moscow"
        assert self.adapter.validate_python("UTC") == "UTC"
        assert self.adapter.validate_python("America/New_York") == "America/New_York"

    def test_default_timezone_is_moscow(self) -> None:
        assert DEFAULT_TIMEZONE == "Europe/Moscow"

    def test_invalid_timezone_raises_error(self) -> None:
        with pytest.raises(InvalidTimezoneError):
            self.adapter.validate_python("Invalid/Unknown_Zone")


class TestPrivacySettingsValueObject:
    """Tests for the PrivacySettings domain model."""

    def test_default_privacy_settings(self) -> None:
        privacy = PrivacySettings.default()
        assert privacy.who_can_see_avatar == PrivacyScope.ALL
        assert privacy.who_can_find_by_username == PrivacyScope.ALL
        assert privacy.who_can_see_bio == PrivacyScope.ALL

    def test_custom_privacy_settings(self) -> None:
        privacy = PrivacySettings(
            who_can_see_avatar=PrivacyScope.NOBODY,
            who_can_find_by_username=PrivacyScope.ALL,
            who_can_see_bio=PrivacyScope.NOBODY,
        )
        assert privacy.who_can_see_avatar == PrivacyScope.NOBODY
        assert privacy.who_can_find_by_username == PrivacyScope.ALL
        assert privacy.who_can_see_bio == PrivacyScope.NOBODY

    def test_invalid_privacy_scope_raises_error(self) -> None:
        with pytest.raises(InvalidPrivacyScopeError):
            PrivacyScope("FRIENDS")


class TestUserProfileStatusValueObject:
    """Tests for the UserProfileStatus enum."""

    def test_status_values(self) -> None:
        assert UserProfileStatus.ACTIVE == "ACTIVE"
        assert UserProfileStatus.DISABLED == "DISABLED"
        assert UserProfileStatus.BLOCKED == "BLOCKED"

    def test_status_default(self) -> None:
        assert UserProfileStatus.default() == UserProfileStatus.ACTIVE

    def test_invalid_status_raises_error(self) -> None:
        with pytest.raises(InvalidProfileStatusError):
            UserProfileStatus("UNKNOWN_STATUS")

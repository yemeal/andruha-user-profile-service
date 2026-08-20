"""Unit tests for Application Layer DTOs (Commands, Queries, Responses) and Base classes."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.application.dto import (
    CheckProfileExistsQuery,
    CreateDefaultProfileCommand,
    GetBatchProfilesQuery,
    GetMyProfileQuery,
    GetMySettingsQuery,
    GetPublicProfileQuery,
    ProfileDTO,
    PublicProfileDTO,
    ResetSettingsCommand,
    SearchByUsernameQuery,
    SettingsDTO,
    UpdateAvatarCommand,
    UpdateProfileCommand,
    UpdateSettingsCommand,
)
from app.domain.aggregates import UserProfile, UserSettings
from app.domain.value_objects import (
    Locale,
    PrivacySettings,
    Theme,
    UserProfileStatus,
)


class TestBaseDTOClasses:
    """Tests for BaseDTO, BaseCommand, BaseQuery, and BaseResponse."""

    def test_base_command_non_none_fields(self) -> None:
        user_id = uuid.uuid4()
        cmd = UpdateProfileCommand(
            user_id=user_id,
            expected_version=2,
            display_name="Alex",
            bio=None,
            username=None,
        )
        # non_none_fields without exclusion
        fields = cmd.non_none_fields()
        assert fields == {
            "user_id": user_id,
            "expected_version": 2,
            "display_name": "Alex",
        }

        # non_none_fields with exclusion of technical fields
        fields_excluded = cmd.non_none_fields(exclude={"user_id", "expected_version"})
        assert fields_excluded == {"display_name": "Alex"}

    def test_base_command_to_dict(self) -> None:
        user_id = uuid.uuid4()
        cmd = ResetSettingsCommand(user_id=user_id, expected_version=1)
        data = cmd.to_dict()
        assert data == {"user_id": user_id, "expected_version": 1}

    def test_base_query_to_params(self) -> None:
        user_id = uuid.uuid4()
        viewer_id = uuid.uuid4()
        query = GetPublicProfileQuery(user_id=user_id, viewer_id=viewer_id)
        params = query.to_params()
        assert params == {"user_id": user_id, "viewer_id": viewer_id}

    def test_base_response_from_domain(self) -> None:
        user_id = uuid.uuid4()
        now = datetime.now(UTC)
        profile = UserProfile.create_default(user_id=user_id, now=now)

        dto = ProfileDTO.from_domain(profile)
        assert dto.user_id == user_id
        assert dto.display_name == "Пользователь"
        assert dto.version == 1

        settings = UserSettings.create_default(user_id=user_id, now=now)
        settings_dto = SettingsDTO.from_domain(settings)
        assert settings_dto.user_id == user_id
        assert settings_dto.theme == Theme.SYSTEM


class TestCommandsDTO:
    """Tests for Command DTOs."""

    def test_create_default_profile_command(self) -> None:
        user_id = uuid.uuid4()
        now = datetime.now(UTC)
        event_id = uuid.uuid4()

        cmd = CreateDefaultProfileCommand(
            user_id=user_id,
            registered_at=now,
            event_id=event_id,
        )
        assert cmd.user_id == user_id
        assert cmd.registered_at == now
        assert cmd.event_id == event_id

        # extra="forbid"
        with pytest.raises(ValidationError):
            CreateDefaultProfileCommand(
                user_id=user_id,
                registered_at=now,
                email="hacked@example.com",  # type: ignore[call-arg]
            )

    def test_update_profile_command_valid(self) -> None:
        user_id = uuid.uuid4()
        cmd = UpdateProfileCommand(
            user_id=user_id,
            expected_version=1,
            display_name="Alex",
            bio="Software Developer",
            username="alex_dev",
        )
        assert cmd.user_id == user_id
        assert cmd.expected_version == 1
        assert cmd.display_name == "Alex"
        assert cmd.bio == "Software Developer"
        assert cmd.username == "alex_dev"

    def test_update_profile_command_invalid_version(self) -> None:
        user_id = uuid.uuid4()
        with pytest.raises(ValidationError):
            UpdateProfileCommand(
                user_id=user_id,
                expected_version=0,  # ge=1 constraint
            )

    def test_update_avatar_command(self) -> None:
        user_id = uuid.uuid4()
        cmd = UpdateAvatarCommand(
            user_id=user_id,
            expected_version=2,
            avatar_key="avatars/user.png",
        )
        assert cmd.avatar_key == "avatars/user.png"

        # None allows removing avatar
        cmd_delete = UpdateAvatarCommand(
            user_id=user_id,
            expected_version=2,
            avatar_key=None,
        )
        assert cmd_delete.avatar_key is None

    def test_update_settings_command(self) -> None:
        user_id = uuid.uuid4()
        cmd = UpdateSettingsCommand(
            user_id=user_id,
            expected_version=3,
            theme="dark",
            locale="ru",
            timezone="Europe/Moscow",
            who_can_see_avatar="ALL",
            who_can_find_by_username="NOBODY",
            who_can_see_bio="ALL",
        )
        assert cmd.theme == "dark"
        assert cmd.who_can_find_by_username == "NOBODY"

    def test_reset_settings_command(self) -> None:
        user_id = uuid.uuid4()
        cmd = ResetSettingsCommand(user_id=user_id, expected_version=5)
        assert cmd.user_id == user_id
        assert cmd.expected_version == 5


class TestQueriesDTO:
    """Tests for Query DTOs."""

    def test_get_my_profile_query(self) -> None:
        user_id = uuid.uuid4()
        query = GetMyProfileQuery(user_id=user_id)
        assert query.user_id == user_id

    def test_get_public_profile_query(self) -> None:
        user_id = uuid.uuid4()
        viewer_id = uuid.uuid4()
        query = GetPublicProfileQuery(user_id=user_id, viewer_id=viewer_id)
        assert query.user_id == user_id
        assert query.viewer_id == viewer_id

    def test_search_by_username_query(self) -> None:
        query = SearchByUsernameQuery(username="alexander")
        assert query.username == "alexander"
        assert query.viewer_id is None

        # Min / max length validation
        with pytest.raises(ValidationError):
            SearchByUsernameQuery(username="ab")

    def test_get_batch_profiles_query_valid_and_deduplicates(self) -> None:
        id1 = uuid.uuid4()
        id2 = uuid.uuid4()
        # id1 is duplicated
        query = GetBatchProfilesQuery(user_ids=[id1, id2, id1])
        assert query.user_ids == [id1, id2]

    def test_get_batch_profiles_query_empty_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            GetBatchProfilesQuery(user_ids=[])

    def test_get_batch_profiles_query_over_100_raises_error(self) -> None:
        ids = [uuid.uuid4() for _ in range(101)]
        with pytest.raises(ValidationError):
            GetBatchProfilesQuery(user_ids=ids)

    def test_check_profile_exists_query(self) -> None:
        user_id = uuid.uuid4()
        query = CheckProfileExistsQuery(user_id=user_id)
        assert query.user_id == user_id

    def test_get_my_settings_query(self) -> None:
        user_id = uuid.uuid4()
        query = GetMySettingsQuery(user_id=user_id)
        assert query.user_id == user_id


class TestResponsesDTO:
    """Tests for Response DTOs."""

    def test_profile_dto_from_domain_aggregate(self) -> None:
        user_id = uuid.uuid4()
        now = datetime.now(UTC)
        profile = UserProfile.create_default(user_id=user_id, now=now)

        dto = ProfileDTO.model_validate(profile)
        assert dto.user_id == user_id
        assert dto.display_name == "Пользователь"
        assert dto.username is None
        assert dto.status == UserProfileStatus.ACTIVE
        assert dto.is_verified is False
        assert dto.version == 1
        assert dto.created_at == now
        assert dto.updated_at is None

    def test_public_profile_dto(self) -> None:
        user_id = uuid.uuid4()
        dto = PublicProfileDTO(
            user_id=user_id,
            username="alex",
            display_name="Alex P",
            bio="Public bio",
            avatar_key="avatars/a.png",
            is_verified=True,
        )
        assert dto.user_id == user_id
        assert dto.display_name == "Alex P"
        assert dto.bio == "Public bio"
        assert dto.avatar_key == "avatars/a.png"
        assert dto.is_verified is True

    def test_settings_dto_from_domain_aggregate(self) -> None:
        user_id = uuid.uuid4()
        now = datetime.now(UTC)
        settings = UserSettings.create_default(user_id=user_id, now=now)

        dto = SettingsDTO.model_validate(settings)
        assert dto.user_id == user_id
        assert dto.theme == Theme.SYSTEM
        assert dto.locale == Locale.RU
        assert dto.timezone == "Europe/Moscow"
        assert dto.privacy == PrivacySettings.default()
        assert dto.version == 1
        assert dto.created_at == now
        assert dto.updated_at is None

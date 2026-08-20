"""Unit tests for Application Layer DTOs (Commands, Queries, Responses) and Base abstractions."""

import uuid
from datetime import UTC, datetime, timedelta

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
    Bio,
    DisplayName,
    Locale,
    PrivacyScope,
    PrivacySettings,
    Theme,
    Username,
    UserProfileStatus,
)


class TestBaseDTOClasses:
    """1. Инварианты базовых классов (BaseDTO, BaseCommand, BaseQuery, BaseResponse)."""

    def test_base_command_non_none_fields(self) -> None:
        user_id = uuid.uuid4()
        cmd = UpdateProfileCommand(
            user_id=user_id,
            expected_version=2,
            display_name="Alex",
            bio=None,
            username=None,
        )
        fields = cmd.non_none_fields()
        assert fields == {
            "user_id": user_id,
            "expected_version": 2,
            "display_name": "Alex",
        }

        fields_excluded = cmd.non_none_fields(exclude={"user_id", "expected_version"})
        assert fields_excluded == {"display_name": "Alex"}

    def test_base_command_non_none_fields_all_none_and_empty(self) -> None:
        user_id = uuid.uuid4()
        cmd = UpdateProfileCommand(
            user_id=user_id,
            expected_version=1,
            display_name=None,
            bio=None,
            username=None,
        )
        fields_excluded = cmd.non_none_fields(exclude={"user_id", "expected_version"})
        assert fields_excluded == {}

    def test_base_command_to_dict(self) -> None:
        user_id = uuid.uuid4()
        cmd = ResetSettingsCommand(user_id=user_id, expected_version=1)
        assert cmd.to_dict() == {"user_id": user_id, "expected_version": 1}

    def test_base_query_to_params(self) -> None:
        user_id = uuid.uuid4()
        viewer_id = uuid.uuid4()
        query = GetPublicProfileQuery(user_id=user_id, viewer_id=viewer_id)
        assert query.to_params() == {"user_id": user_id, "viewer_id": viewer_id}

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

    def test_base_dto_immutability(self) -> None:
        user_id = uuid.uuid4()
        cmd = UpdateProfileCommand(
            user_id=user_id,
            expected_version=1,
            display_name="Alex",
        )
        with pytest.raises(ValidationError):
            cmd.display_name = "NewName"  # type: ignore[misc]

        query = GetMyProfileQuery(user_id=user_id)
        with pytest.raises(ValidationError):
            query.user_id = uuid.uuid4()  # type: ignore[misc]

        dto = PublicProfileDTO(
            user_id=user_id,
            username="alex",
            display_name="Alex",
            bio=None,
            avatar_key=None,
            is_verified=False,
        )
        with pytest.raises(ValidationError):
            dto.display_name = "Mutated"  # type: ignore[misc]

    def test_base_command_extra_forbid(self) -> None:
        user_id = uuid.uuid4()
        now = datetime.now(UTC)

        with pytest.raises(ValidationError):
            CreateDefaultProfileCommand(
                user_id=user_id,
                registered_at=now,
                unknown_field="injected",  # type: ignore[call-arg]
            )

        with pytest.raises(ValidationError):
            UpdateProfileCommand(
                user_id=user_id,
                expected_version=1,
                password_hash="leaked",  # type: ignore[call-arg]
            )

        with pytest.raises(ValidationError):
            UpdateAvatarCommand(
                user_id=user_id,
                expected_version=1,
                extra_payload=123,  # type: ignore[call-arg]
            )

        with pytest.raises(ValidationError):
            UpdateSettingsCommand(
                user_id=user_id,
                expected_version=1,
                role="admin",  # type: ignore[call-arg]
            )

        with pytest.raises(ValidationError):
            ResetSettingsCommand(
                user_id=user_id,
                expected_version=1,
                cheat_code=True,  # type: ignore[call-arg]
            )

    def test_base_query_extra_forbid(self) -> None:
        user_id = uuid.uuid4()

        with pytest.raises(ValidationError):
            GetMyProfileQuery(
                user_id=user_id,
                unexpected="extra",  # type: ignore[call-arg]
            )

        with pytest.raises(ValidationError):
            GetPublicProfileQuery(
                user_id=user_id,
                sql_injection="DROP TABLE profiles",  # type: ignore[call-arg]
            )

        with pytest.raises(ValidationError):
            SearchByUsernameQuery(
                username="alex",
                limit=10,  # type: ignore[call-arg]
            )

        with pytest.raises(ValidationError):
            CheckProfileExistsQuery(
                user_id=user_id,
                internal_token="secret",  # type: ignore[call-arg]
            )

        with pytest.raises(ValidationError):
            GetMySettingsQuery(
                user_id=user_id,
                device="mobile",  # type: ignore[call-arg]
            )


class TestCommandsDTO:
    """2. Валидация и парсинг команд (TestCommandsDTO)."""

    def test_create_default_profile_command_valid(self) -> None:
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

    def test_create_default_profile_command_string_coercion_and_parsing(self) -> None:
        user_id_str = "01912a75-7b23-74e2-8951-40be317130a1"
        registered_at_str = "2026-08-21T05:00:00.000Z"
        event_id_str = "01912a75-7b23-74e2-8951-40be317130a2"

        data = {
            "user_id": user_id_str,
            "registered_at": registered_at_str,
            "event_id": event_id_str,
        }
        cmd = CreateDefaultProfileCommand.model_validate(data)
        assert cmd.user_id == uuid.UUID(user_id_str)
        assert cmd.event_id == uuid.UUID(event_id_str)
        assert isinstance(cmd.registered_at, datetime)

    def test_create_default_profile_command_invalid_uuid(self) -> None:
        with pytest.raises(ValidationError):
            CreateDefaultProfileCommand.model_validate({
                "user_id": "not-a-valid-uuid",
                "registered_at": datetime.now(UTC).isoformat(),
            })

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

    def test_update_profile_command_boundary_version_1(self) -> None:
        user_id = uuid.uuid4()
        cmd = UpdateProfileCommand(user_id=user_id, expected_version=1)
        assert cmd.expected_version == 1

    @pytest.mark.parametrize("invalid_ver", [0, -1, -100])
    def test_update_profile_command_invalid_versions(self, invalid_ver: int) -> None:
        user_id = uuid.uuid4()
        with pytest.raises(ValidationError):
            UpdateProfileCommand(
                user_id=user_id,
                expected_version=invalid_ver,
            )

    def test_update_avatar_command(self) -> None:
        user_id = uuid.uuid4()
        cmd = UpdateAvatarCommand(
            user_id=user_id,
            expected_version=2,
            avatar_key="avatars/user.png",
        )
        assert cmd.avatar_key == "avatars/user.png"

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

    def test_reset_settings_command_valid(self) -> None:
        user_id = uuid.uuid4()
        cmd = ResetSettingsCommand(user_id=user_id, expected_version=5)
        assert cmd.user_id == user_id
        assert cmd.expected_version == 5

    @pytest.mark.parametrize("invalid_ver", [0, -5])
    def test_reset_settings_command_invalid_version(self, invalid_ver: int) -> None:
        user_id = uuid.uuid4()
        with pytest.raises(ValidationError):
            ResetSettingsCommand(user_id=user_id, expected_version=invalid_ver)


class TestQueriesDTO:
    """3. Границы и ограничения запросов (TestQueriesDTO)."""

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

    @pytest.mark.parametrize("valid_username", ["abc", "a" * 32, "user_123"])
    def test_search_by_username_query_valid_boundary_lengths(
        self, valid_username: str
    ) -> None:
        """Проверка валидных граничных длин никнейма (3 символа, 32 символа)."""
        query = SearchByUsernameQuery(username=valid_username)
        assert query.username == valid_username

    @pytest.mark.parametrize(
        "invalid_username",
        ["", "a", "ab", "a" * 33, "a" * 50],
    )
    def test_search_by_username_query_invalid_boundary_lengths(
        self, invalid_username: str
    ) -> None:
        """Проверка выхода за границы длины никнейма (< 3 и > 32 символов)."""
        with pytest.raises(ValidationError):
            SearchByUsernameQuery(username=invalid_username)

    def test_search_by_username_query_string_coercion(self) -> None:
        viewer_id_str = "01912a75-7b23-74e2-8951-40be317130a1"
        data = {"username": "alexander", "viewer_id": viewer_id_str}
        query = SearchByUsernameQuery.model_validate(data)
        assert query.username == "alexander"
        assert query.viewer_id == uuid.UUID(viewer_id_str)

    def test_get_batch_profiles_query_boundary_limits(self) -> None:
        # Ровно 1 элемент — валидная нижняя граница
        q1 = GetBatchProfilesQuery(user_ids=[uuid.uuid4()])
        assert len(q1.user_ids) == 1

        # Ровно 100 уникальных элементов — валидная верхняя граница
        hundred_ids = [uuid.uuid4() for _ in range(100)]
        q100 = GetBatchProfilesQuery(user_ids=hundred_ids)
        assert len(q100.user_ids) == 100

        # Больше 100 уникальных элементов — ошибка
        with pytest.raises(ValidationError):
            GetBatchProfilesQuery(user_ids=[uuid.uuid4() for _ in range(101)])

        # Пустой список — ошибка
        with pytest.raises(ValidationError):
            GetBatchProfilesQuery(user_ids=[])

    def test_get_batch_profiles_query_deduplication(self) -> None:
        id1 = uuid.uuid4()
        id2 = uuid.uuid4()
        id3 = uuid.uuid4()
        query = GetBatchProfilesQuery(user_ids=[id1, id2, id1, id3, id2])
        assert query.user_ids == [id1, id2, id3]

    def test_get_batch_profiles_query_invalid_uuid_item(self) -> None:
        with pytest.raises(ValidationError):
            GetBatchProfilesQuery.model_validate({"user_ids": ["not-a-uuid"]})

    def test_check_profile_exists_query(self) -> None:
        user_id = uuid.uuid4()
        query = CheckProfileExistsQuery(user_id=user_id)
        assert query.user_id == user_id

    def test_get_my_settings_query(self) -> None:
        user_id = uuid.uuid4()
        query = GetMySettingsQuery(user_id=user_id)
        assert query.user_id == user_id


class TestResponsesDTO:
    """4. Ответы и маппинг (TestResponsesDTO)."""

    def test_profile_dto_from_domain_aggregate(self) -> None:
        user_id = uuid.uuid4()
        now = datetime.now(UTC)
        profile = UserProfile.create_default(user_id=user_id, now=now)

        dto = ProfileDTO.from_domain(profile)
        assert dto.user_id == user_id
        assert dto.display_name == "Пользователь"
        assert dto.username is None
        assert dto.bio is None
        assert dto.avatar_key is None
        assert dto.status == UserProfileStatus.ACTIVE
        assert dto.is_verified is False
        assert dto.version == 1
        assert dto.created_at == now
        assert dto.updated_at is None

    def test_profile_dto_from_domain_with_optional_fields(self) -> None:
        user_id = uuid.uuid4()
        created_at = datetime.now(UTC)
        profile = UserProfile.create_default(user_id=user_id, now=created_at)

        updated_at = created_at + timedelta(minutes=5)
        profile.update_profile(
            display_name=DisplayName("Alex Developer"),
            bio=Bio("Building distributed systems"),
            username=Username("alex_dev"),
            now=updated_at,
        )
        profile.update_avatar(avatar_key="avatars/alex.png", now=updated_at)

        dto = ProfileDTO.from_domain(profile)
        assert dto.user_id == user_id
        assert dto.display_name == "Alex Developer"
        assert dto.bio == "Building distributed systems"
        assert dto.username == "alex_dev"
        assert dto.avatar_key == "avatars/alex.png"
        assert dto.version == 3  # create(1) + update_profile(2) + update_avatar(3)
        assert dto.created_at == created_at
        assert dto.updated_at == updated_at

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

    def test_public_profile_dto_minimal_and_none_fields(self) -> None:
        user_id = uuid.uuid4()
        dto = PublicProfileDTO(
            user_id=user_id,
            username=None,
            display_name="Guest User",
            bio=None,
            avatar_key=None,
            is_verified=False,
        )
        assert dto.user_id == user_id
        assert dto.username is None
        assert dto.display_name == "Guest User"
        assert dto.bio is None
        assert dto.avatar_key is None
        assert dto.is_verified is False

    def test_settings_dto_from_domain_aggregate(self) -> None:
        user_id = uuid.uuid4()
        now = datetime.now(UTC)
        settings = UserSettings.create_default(user_id=user_id, now=now)

        dto = SettingsDTO.from_domain(settings)
        assert dto.user_id == user_id
        assert dto.theme == Theme.SYSTEM
        assert dto.locale == Locale.RU
        assert dto.timezone == "Europe/Moscow"
        assert dto.privacy == PrivacySettings.default()
        assert dto.version == 1
        assert dto.created_at == now
        assert dto.updated_at is None

    def test_settings_dto_from_domain_with_updated_at(self) -> None:
        user_id = uuid.uuid4()
        created_at = datetime.now(UTC)
        settings = UserSettings.create_default(user_id=user_id, now=created_at)

        updated_at = created_at + timedelta(hours=1)
        settings.update_settings(
            theme=Theme.DARK,
            locale=Locale.EN,
            timezone="UTC",
            privacy=PrivacySettings(
                who_can_see_avatar=PrivacyScope.NOBODY,
                who_can_find_by_username=PrivacyScope.NOBODY,
                who_can_see_bio=PrivacyScope.NOBODY,
            ),
            now=updated_at,
        )

        dto = SettingsDTO.from_domain(settings)
        assert dto.user_id == user_id
        assert dto.theme == Theme.DARK
        assert dto.locale == Locale.EN
        assert dto.timezone == "UTC"
        assert dto.privacy.who_can_see_avatar == PrivacyScope.NOBODY
        assert dto.version == 2
        assert dto.created_at == created_at
        assert dto.updated_at == updated_at

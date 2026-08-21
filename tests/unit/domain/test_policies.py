"""Unit tests for Domain Policies (ProfilePrivacyPolicy)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.aggregates.settings import UserSettings
from app.domain.policies.privacy import ProfilePrivacyPolicy
from app.domain.value_objects.privacy import PrivacyScope, PrivacySettings


class TestProfilePrivacyPolicy:
    """Tests for ProfilePrivacyPolicy permissions."""

    @pytest.fixture
    def target_user_id(self) -> uuid.UUID:
        return uuid.uuid4()

    @pytest.fixture
    def default_settings(self, target_user_id: uuid.UUID) -> UserSettings:
        return UserSettings.create_default(
            user_id=target_user_id,
            now=datetime.now(UTC),
        )

    @pytest.fixture
    def strict_privacy_settings(self, target_user_id: uuid.UUID) -> UserSettings:
        created_at = datetime.now(UTC)
        settings = UserSettings.create_default(user_id=target_user_id, now=created_at)
        updated_at = created_at + timedelta(seconds=10)
        settings.update_settings(
            privacy=PrivacySettings(
                who_can_see_avatar=PrivacyScope.NOBODY,
                who_can_find_by_username=PrivacyScope.NOBODY,
                who_can_see_bio=PrivacyScope.NOBODY,
            ),
            now=updated_at,
        )
        return settings

    def test_owner_can_always_view_everything(
        self, target_user_id: uuid.UUID, strict_privacy_settings: UserSettings
    ) -> None:
        """Владелец профиля всегда видит свои данные даже при строгой приватности (NOBODY)."""
        assert (
            ProfilePrivacyPolicy.can_view_bio(
                target_user_id=target_user_id,
                settings=strict_privacy_settings,
                viewer_id=target_user_id,
            )
            is True
        )

        assert (
            ProfilePrivacyPolicy.can_view_avatar(
                target_user_id=target_user_id,
                settings=strict_privacy_settings,
                viewer_id=target_user_id,
            )
            is True
        )

        assert (
            ProfilePrivacyPolicy.can_find_by_username(
                target_user_id=target_user_id,
                settings=strict_privacy_settings,
                viewer_id=target_user_id,
            )
            is True
        )

    def test_external_viewer_with_default_all_privacy(
        self, target_user_id: uuid.UUID, default_settings: UserSettings
    ) -> None:
        """Посторонний пользователь видит данные, если настройки установлены в ALL."""
        external_viewer_id = uuid.uuid4()

        assert (
            ProfilePrivacyPolicy.can_view_bio(
                target_user_id=target_user_id,
                settings=default_settings,
                viewer_id=external_viewer_id,
            )
            is True
        )

        assert (
            ProfilePrivacyPolicy.can_view_avatar(
                target_user_id=target_user_id,
                settings=default_settings,
                viewer_id=external_viewer_id,
            )
            is True
        )

        assert (
            ProfilePrivacyPolicy.can_find_by_username(
                target_user_id=target_user_id,
                settings=default_settings,
                viewer_id=external_viewer_id,
            )
            is True
        )

    def test_external_viewer_with_strict_nobody_privacy(
        self, target_user_id: uuid.UUID, strict_privacy_settings: UserSettings
    ) -> None:
        """Посторонний пользователь не видит данные, если настройки установлены в NOBODY."""
        external_viewer_id = uuid.uuid4()

        assert (
            ProfilePrivacyPolicy.can_view_bio(
                target_user_id=target_user_id,
                settings=strict_privacy_settings,
                viewer_id=external_viewer_id,
            )
            is False
        )

        assert (
            ProfilePrivacyPolicy.can_view_avatar(
                target_user_id=target_user_id,
                settings=strict_privacy_settings,
                viewer_id=external_viewer_id,
            )
            is False
        )

        assert (
            ProfilePrivacyPolicy.can_find_by_username(
                target_user_id=target_user_id,
                settings=strict_privacy_settings,
                viewer_id=external_viewer_id,
            )
            is False
        )

    def test_anonymous_viewer_without_viewer_id(
        self,
        target_user_id: uuid.UUID,
        default_settings: UserSettings,
        strict_privacy_settings: UserSettings,
    ) -> None:
        """Неавторизованный гость (viewer_id=None)."""
        # При ALL — разрешено
        assert (
            ProfilePrivacyPolicy.can_view_bio(
                target_user_id=target_user_id,
                settings=default_settings,
                viewer_id=None,
            )
            is True
        )

        # При NOBODY — запрещено
        assert (
            ProfilePrivacyPolicy.can_view_bio(
                target_user_id=target_user_id,
                settings=strict_privacy_settings,
                viewer_id=None,
            )
            is False
        )

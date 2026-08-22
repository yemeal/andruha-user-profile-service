from __future__ import annotations

import uuid
from datetime import datetime
from typing import Self

from pydantic import Field

from app.application.dto.base import BaseDTO
from app.domain.aggregates.profiles import UserProfile
from app.domain.aggregates.settings import UserSettings
from app.domain.policies.privacy import ProfilePrivacyPolicy
from app.domain.value_objects.status import UserProfileStatus


class ProfileDTO(BaseDTO):
    """
    Полное представление профиля пользователя (для владельца).
    """

    user_id: uuid.UUID = Field(
        description="Уникальный идентификатор пользователя (UUIDv7)",
    )
    username: str | None = Field(
        default=None,
        description="Уникальный никнейм пользователя",
    )
    display_name: str = Field(
        description="Отображаемое имя профиля",
    )
    bio: str | None = Field(
        default=None,
        description="Краткое описание/биография профиля",
    )
    avatar_key: str | None = Field(
        default=None,
        description="Ключ аватара в объектном хранилище",
    )
    status: UserProfileStatus = Field(
        description="Текущий статус жизненного цикла профиля (ACTIVE, DISABLED, BLOCKED)",
    )
    is_verified: bool = Field(
        description="Флаг верификации профиля",
    )
    version: int = Field(
        description="Текущий номер версии профиля для оптимистической блокировки (OCC)",
    )
    created_at: datetime = Field(
        description="Дата создания профиля (UTC)",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="Дата последнего обновления профиля (UTC)",
    )


class PublicProfileDTO(BaseDTO):
    """
    Публичное представление профиля для третьих лиц.
    Поля bio и avatar_key маскируются в None, если настройки приватности целевого
    пользователя ограничивают их видимость.
    """

    user_id: uuid.UUID = Field(
        description="Уникальный идентификатор пользователя (UUIDv7)",
    )
    username: str | None = Field(
        default=None,
        description="Уникальный никнейм пользователя",
    )
    display_name: str = Field(
        description="Отображаемое имя профиля",
    )
    bio: str | None = Field(
        default=None,
        description="Описание профиля (скрыто, если ограничено приватностью)",
    )
    avatar_key: str | None = Field(
        default=None,
        description="Ключ аватара (скрыт, если ограничен приватностью)",
    )
    is_verified: bool = Field(
        description="Флаг верификации профиля",
    )

    @classmethod
    def from_domain_with_policy(
        cls,
        profile: UserProfile,
        settings: UserSettings,
        viewer_id: uuid.UUID | None = None,
    ) -> Self:
        """
        Фабричный метод создания публичного DTO с применением доменной политики приватности.
        """
        can_bio = ProfilePrivacyPolicy.can_view_bio(
            target_user_id=profile.id,
            settings=settings,
            viewer_id=viewer_id,
        )
        can_avatar = ProfilePrivacyPolicy.can_view_avatar(
            target_user_id=profile.id,
            settings=settings,
            viewer_id=viewer_id,
        )
        return cls(
            user_id=profile.id,
            username=str(profile.username) if profile.username else None,
            display_name=str(profile.display_name),
            bio=str(profile.bio) if (profile.bio and can_bio) else None,
            avatar_key=profile.avatar_key if can_avatar else None,
            is_verified=profile.is_verified,
        )

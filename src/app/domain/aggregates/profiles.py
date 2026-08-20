import uuid
from datetime import datetime

from pydantic import Field

from app.domain.base import VersionedMutableEntity
from app.domain.value_objects.bio import Bio
from app.domain.value_objects.display_name import (
    DEFAULT_DISPLAY_NAME,
    DisplayName,
)
from app.domain.value_objects.status import UserProfileStatus
from app.domain.value_objects.username import Username


class UserProfile(VersionedMutableEntity):
    """Агрегат профиля пользователя (UserProfile Aggregate Root)."""

    id: uuid.UUID = Field(
        validation_alias="user_id",
        default_factory=uuid.uuid7,
        description="Уникальный идентификатор пользователя (UUIDv7)",
    )
    username: Username | None = Field(
        default=None,
        description="Уникальный публичный никнейм пользователя",
    )
    display_name: DisplayName = Field(
        default=DEFAULT_DISPLAY_NAME,
        description="Отображаемое имя профиля",
    )
    bio: Bio | None = Field(
        default=None,
        description="Краткое описание/биография профиля",
    )
    avatar_key: str | None = Field(
        default=None,
        description="Ключ/путь к аватару в объектном хранилище",
    )
    status: UserProfileStatus = Field(
        default=UserProfileStatus.ACTIVE,
        description="Текущий статус жизненного цикла профиля",
    )
    is_verified: bool = Field(
        default=False,
        description="Флаг верификации профиля администрацией",
    )

    @property
    def user_id(self) -> uuid.UUID:
        """Псевдоним id для агрегата профиля пользователя."""
        return self.id

    @property
    def is_active(self) -> bool:
        """Активен ли профиль для взаимодействия."""
        return self.status == UserProfileStatus.ACTIVE

    @property
    def is_blocked(self) -> bool:
        """Заблокирован ли профиль администратором."""
        return self.status == UserProfileStatus.BLOCKED

    def deactivate(self, now: datetime) -> None:
        """Деактивация профиля пользователем."""
        if self.status != UserProfileStatus.DISABLED:
            self.status = UserProfileStatus.DISABLED
            self.mark_updated(now)

    def block(self, now: datetime) -> None:
        """Блокировка профиля администратором."""
        if self.status != UserProfileStatus.BLOCKED:
            self.status = UserProfileStatus.BLOCKED
            self.mark_updated(now)

    def activate(self, now: datetime) -> None:
        """Повторная активация профиля."""
        if self.status != UserProfileStatus.ACTIVE:
            self.status = UserProfileStatus.ACTIVE
            self.mark_updated(now)

    @classmethod
    def create_default(cls, user_id: uuid.UUID, now: datetime) -> UserProfile:
        """Фабрика для создания дефолтного профиля-заглушки (username изначально None)."""
        return cls(
            id=user_id,
            username=None,
            display_name=DEFAULT_DISPLAY_NAME,
            bio=None,
            avatar_key=None,
            status=UserProfileStatus.ACTIVE,
            is_verified=False,
            version=1,
            created_at=now,
            updated_at=None,
        )

    def update_profile(
        self,
        *,
        now: datetime,
        display_name: str | None = None,
        bio: str | None = None,
        username: str | None = None,
    ) -> bool:
        """Обновляет изменяемые поля профиля. Возвращает True, если было реальное изменение."""
        changed = False

        if display_name is not None and display_name.strip() != self.display_name:
            self.display_name = display_name
            changed = True

        if bio is not None:
            normalized_bio = bio if bio else None
            if normalized_bio != self.bio:
                self.bio = normalized_bio
                changed = True

        if username is not None:
            candidate_username = Username(username)
            if candidate_username != self.username:
                self.username = candidate_username
                changed = True

        if changed:
            self.mark_updated(now)

        return changed

    def update_avatar(self, avatar_key: str | None, now: datetime) -> bool:
        """Обновляет или удаляет (None) ключ аватара."""
        changed = False

        if self.avatar_key != avatar_key:
            self.avatar_key = avatar_key
            self.mark_updated(now)
            changed = True

        return changed

    def verify(self, now: datetime) -> None:
        """Выдача подтверждённого статуса."""
        if not self.is_verified:
            self.is_verified = True
            self.mark_updated(now)

    def unverify(self, now: datetime) -> None:
        """Снятие подтверждённого статуса."""
        if self.is_verified:
            self.is_verified = False
            self.mark_updated(now)

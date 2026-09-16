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
        frozen=True,
        validation_alias="user_id",
        default_factory=uuid.uuid7,
        description="Уникальный идентификатор пользователя (UUIDv7)",
    )
    username: Username | None = Field(
        frozen=True,
        default=None,
        description="Уникальный публичный никнейм пользователя",
    )
    display_name: DisplayName = Field(
        frozen=True,
        default=DEFAULT_DISPLAY_NAME,
        description="Отображаемое имя профиля",
    )
    bio: Bio | None = Field(
        frozen=True,
        default=None,
        description="Краткое описание/биография профиля",
    )
    avatar_key: str | None = Field(
        frozen=True,
        default=None,
        description="Ключ/путь к аватару в объектном хранилище",
    )
    status: UserProfileStatus = Field(
        frozen=True,
        default=UserProfileStatus.ACTIVE,
        description="Текущий статус жизненного цикла профиля",
    )
    is_verified: bool = Field(
        frozen=True,
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
        self._apply_changes(now=now, status=UserProfileStatus.DISABLED)

    def block(self, now: datetime) -> None:
        """Блокировка профиля администратором."""
        self._apply_changes(now=now, status=UserProfileStatus.BLOCKED)

    def activate(self, now: datetime) -> None:
        """Повторная активация профиля."""
        self._apply_changes(now=now, status=UserProfileStatus.ACTIVE)

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
        return self._apply_changes(
            now=now,
            display_name=self.display_name if display_name is None else display_name,
            bio=self.bio if bio is None else (bio or None),
            username=self.username if username is None else username,
        )

    def update_avatar(self, avatar_key: str | None, now: datetime) -> bool:
        """Обновляет или удаляет (None) ключ аватара."""
        return self._apply_changes(now=now, avatar_key=avatar_key)

    def verify(self, now: datetime) -> None:
        """Выдача подтверждённого статуса."""
        self._apply_changes(now=now, is_verified=True)

    def unverify(self, now: datetime) -> None:
        """Снятие подтверждённого статуса."""
        self._apply_changes(now=now, is_verified=False)

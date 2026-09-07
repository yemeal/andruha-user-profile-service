"""Adapters for handler tests; no handler or business use-case implementation."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import Any
from uuid import UUID

import pytest

from app.domain.aggregates.profiles import UserProfile
from app.domain.aggregates.settings import UserSettings
from app.domain.exceptions.user_profile import (
    ProfileVersionMismatchError,
    UsernameAlreadyTakenError,
    UserProfileNotFoundError,
)
from app.domain.exceptions.user_settings import (
    SettingsVersionMismatchError,
    UserSettingsNotFoundError,
)
from app.domain.value_objects.username import Username

USER_ID = UUID("0194d000-0000-7000-8000-000000000001")
OTHER_USER_ID = UUID("0194d000-0000-7000-8000-000000000002")
NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


class MemoryRepository[EntityT: (UserProfile, UserSettings)]:
    """Copy-on-read/write prevents an unsaved mutation from looking persisted.

    This adapter models the existing persistence port, not SQL transactions.
    No commit/rollback/idempotency methods are exposed to handlers.
    """

    def __init__(
        self, model: type[EntityT], missing: type[Exception], conflict: type[Exception]
    ):
        self._model = model
        self._missing = missing
        self._conflict = conflict
        self._rows: dict[UUID, EntityT] = {}
        self._competing_write: EntityT | None = None

    def seed(self, entity: EntityT) -> None:
        self._rows[entity.id] = entity.model_copy(deep=True)

    def arrange_competing_write(self, entity: EntityT) -> None:
        """Simulate a committed concurrent write just before the next UPDATE."""
        self._competing_write = entity.model_copy(deep=True)

    def _check_unique_username(self, entity: EntityT) -> None:
        if isinstance(entity, UserProfile) and entity.username is not None:
            for current in self._rows.values():
                if (
                    isinstance(current, UserProfile)
                    and current.id != entity.id
                    and current.username == entity.username
                ):
                    raise UsernameAlreadyTakenError()

    async def create(self, entity: EntityT) -> EntityT:
        if entity.id in self._rows:
            raise ValueError("Entity already exists")
        self._check_unique_username(entity)
        self.seed(entity)
        return entity.model_copy(deep=True)

    async def get_by_id(self, entity_id: UUID) -> EntityT | None:
        found = self._rows.get(entity_id)
        return found.model_copy(deep=True) if found is not None else None

    async def create_default_if_absent(self, user_id: UUID, now: datetime) -> EntityT:
        existing = await self.get_by_id(user_id)
        if existing is not None:
            return existing
        return await self.create(self._model.create_default(user_id, now))

    async def update(
        self, entity: EntityT, *, expected_version: int | None = None
    ) -> EntityT:
        if self._competing_write is not None:
            self.seed(self._competing_write)
            self._competing_write = None
        current = self._rows.get(entity.id)
        if current is None:
            raise self._missing()
        if expected_version is not None and current.version != expected_version:
            raise self._conflict()
        self._check_unique_username(entity)
        self.seed(entity)
        return entity.model_copy(deep=True)

    async def delete(self, entity_id: UUID) -> bool:
        return self._rows.pop(entity_id, None) is not None

    async def exists(self, entity_id: UUID) -> bool:
        return entity_id in self._rows

    async def get_batch(self, user_ids: Sequence[UUID]) -> list[EntityT]:
        # The reader contract promises no ordering; do not let fixture order imply it.
        return [
            entity.model_copy(deep=True)
            for key, entity in self._rows.items()
            if key in user_ids
        ]


class ProfileReader:
    """Only the ProfileReaderProtocol surface; no mutation methods."""

    def __init__(self, repository: MemoryRepository[UserProfile]):
        self._repository = repository

    async def get_by_id(self, user_id: UUID) -> UserProfile | None:
        return await self._repository.get_by_id(user_id)

    async def get_by_username(self, username: Username | str) -> UserProfile | None:
        for profile in self._repository._rows.values():
            if profile.username == username:
                return profile.model_copy(deep=True)
        return None

    async def get_batch(self, user_ids: Sequence[UUID]) -> list[UserProfile]:
        return await self._repository.get_batch(user_ids)

    async def exists(self, user_id: UUID) -> bool:
        return await self._repository.exists(user_id)


class SettingsReader:
    """Only the SettingsReaderProtocol surface; no mutation methods."""

    def __init__(self, repository: MemoryRepository[UserSettings]):
        self._repository = repository

    async def get_by_id(self, user_id: UUID) -> UserSettings | None:
        return await self._repository.get_by_id(user_id)


# The only place coupled to class names / constructors of future handlers.
# The public behavior under test is always: await handler(command_or_query).
HANDLERS = {
    "commands/profiles/create_default": (
        "CreateDefaultProfileHandler",
        ("profiles", "settings"),
    ),
    "commands/profiles/update": ("UpdateProfileHandler", ("profiles", "clock")),
    "commands/profiles/update_avatar": ("UpdateAvatarHandler", ("profiles", "clock")),
    "commands/settings/update": ("UpdateSettingsHandler", ("settings", "clock")),
    "commands/settings/reset": ("ResetSettingsHandler", ("settings", "clock")),
    "queries/profiles/get_my": ("GetMyProfileHandler", ("profiles",)),
    "queries/profiles/get_public": (
        "GetPublicProfileHandler",
        ("profiles", "settings"),
    ),
    "queries/profiles/search_by_username": (
        "SearchByUsernameHandler",
        ("profiles", "settings"),
    ),
    "queries/profiles/get_batch": ("GetBatchProfilesHandler", ("profiles", "settings")),
    "queries/profiles/check_exists": ("CheckProfileExistsHandler", ("profiles",)),
    "queries/settings/get_my": ("GetMySettingsHandler", ("settings",)),
}


class HandlerHarness:
    def __init__(self):
        self.user_id = USER_ID
        self.other_user_id = OTHER_USER_ID
        self.now = NOW
        self.clock: Callable[[], datetime] = lambda: self.now
        self.profiles = MemoryRepository(
            UserProfile, UserProfileNotFoundError, ProfileVersionMismatchError
        )
        self.settings = MemoryRepository(
            UserSettings, UserSettingsNotFoundError, SettingsVersionMismatchError
        )

    def seed_profile(
        self, *, user_id: UUID | None = None, **fields: Any
    ) -> UserProfile:
        profile = UserProfile.model_validate(
            {
                "id": user_id or self.user_id,
                "created_at": self.now - timedelta(days=1),
                **fields,
            }
        )
        self.profiles.seed(profile)
        return profile.model_copy(deep=True)

    def seed_settings(
        self, *, user_id: UUID | None = None, **fields: Any
    ) -> UserSettings:
        settings = UserSettings.model_validate(
            {
                "id": user_id or self.user_id,
                "created_at": self.now - timedelta(days=1),
                **fields,
            }
        )
        self.settings.seed(settings)
        return settings.model_copy(deep=True)

    def handler(self, key: str):
        """Fail in the test body, not during collection, until the handler exists."""
        class_name, dependency_names = HANDLERS[key]
        module_name = "app.application." + key.replace("/", ".") + ".handler"
        module = None
        try:
            module = import_module(module_name)
        except ModuleNotFoundError as error:
            if error.name != module_name:
                raise  # A missing dependency inside an existing handler is a real bug.
        if module is None:
            pytest.fail(
                f"RED: implement src/app/application/{key}/handler.py :: {class_name}; "
                "constructor contract: tests/handlers_tdd/support.py:HANDLERS",
                pytrace=False,
            )
        handler_type = getattr(module, class_name, None)
        if handler_type is None:
            pytest.fail(f"RED: {module_name} must expose {class_name}", pytrace=False)
        dependencies = {
            "profiles": ProfileReader(self.profiles)
            if key.startswith("queries/")
            else self.profiles,
            "settings": SettingsReader(self.settings)
            if key.startswith("queries/")
            else self.settings,
            "clock": self.clock,
        }
        return handler_type(**{name: dependencies[name] for name in dependency_names})

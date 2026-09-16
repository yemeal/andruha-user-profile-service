"""Transport payloads; the viewer identity never comes from request data."""

from typing import ClassVar, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.value_objects.locale import Locale
from app.domain.value_objects.privacy import PrivacyScope
from app.domain.value_objects.theme import Theme


class BatchProfilesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_ids: list[UUID] = Field(min_length=1, max_length=100)


class PatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nullable_fields: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        for name in self.model_fields_set - self.nullable_fields:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class ProfilePatchRequest(PatchRequest):
    nullable_fields: ClassVar[frozenset[str]] = frozenset({"bio"})

    display_name: str | None = Field(default=None, min_length=1, max_length=64)
    bio: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, min_length=3, max_length=32)


class PrivacyPatchRequest(PatchRequest):
    who_can_see_avatar: PrivacyScope | None = None
    who_can_find_by_username: PrivacyScope | None = None
    who_can_see_bio: PrivacyScope | None = None


class SettingsPatchRequest(PatchRequest):
    theme: Theme | None = None
    locale: Locale | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    privacy: PrivacyPatchRequest | None = None

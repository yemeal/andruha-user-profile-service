from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models.base import Base


class SettingsORM(Base):
    __tablename__ = "user_settings"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_user_settings_version"),
        CheckConstraint(
            "updated_at IS NULL OR updated_at > created_at",
            name="ck_user_settings_timestamps",
        ),
        CheckConstraint(
            "theme IN ('light', 'dark', 'system')", name="ck_settings_theme"
        ),
        CheckConstraint("locale IN ('ru', 'en')", name="ck_settings_locale"),
        CheckConstraint(
            "jsonb_typeof(privacy) = 'object' "
            "AND privacy ?& ARRAY['who_can_see_avatar', 'who_can_find_by_username', 'who_can_see_bio'] "
            "AND privacy - ARRAY['who_can_see_avatar', 'who_can_find_by_username', 'who_can_see_bio'] = '{}'::jsonb "
            "AND privacy->>'who_can_see_avatar' IN ('ALL', 'NOBODY') "
            "AND privacy->>'who_can_find_by_username' IN ('ALL', 'NOBODY') "
            "AND privacy->>'who_can_see_bio' IN ('ALL', 'NOBODY') "
            "AND NOT privacy @> '{\"who_can_see_avatar\": null}'::jsonb "
            "AND NOT privacy @> '{\"who_can_find_by_username\": null}'::jsonb "
            "AND NOT privacy @> '{\"who_can_see_bio\": null}'::jsonb",
            name="ck_settings_privacy",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    theme: Mapped[str] = mapped_column(String(6))
    locale: Mapped[str] = mapped_column(String(2))
    timezone: Mapped[str] = mapped_column(Text)
    privacy: Mapped[dict[str, Any]] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

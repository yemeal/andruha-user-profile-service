from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models.base import Base


class ProfileORM(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_profiles_version"),
        CheckConstraint(
            "updated_at IS NULL OR updated_at > created_at",
            name="ck_profiles_timestamps",
        ),
        CheckConstraint(
            "length(btrim(display_name)) BETWEEN 1 AND 64",
            name="ck_profiles_display_name",
        ),
        CheckConstraint(
            "bio IS NULL OR (length(bio) <= 255 AND position(chr(10) in bio) = 0 "
            "AND position(chr(13) in bio) = 0)",
            name="ck_profiles_bio",
        ),
        CheckConstraint(
            "username IS NULL OR username ~ '^[a-z0-9_]{3,32}$'",
            name="ck_profiles_username",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'DISABLED', 'BLOCKED')", name="ck_profiles_status"
        ),
    )

    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    username: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(64))
    bio: Mapped[str | None] = mapped_column(String(255))
    avatar_key: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(8))
    is_verified: Mapped[bool] = mapped_column(Boolean)
    version: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

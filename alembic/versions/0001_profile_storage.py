"""create profile settings and durable idempotency"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.String(length=255), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("key_digest", sa.LargeBinary(length=32), nullable=False),
        sa.Column("request_fingerprint", sa.LargeBinary(length=32), nullable=False),
        sa.Column(
            "fingerprint_version", sa.SmallInteger(), server_default="1", nullable=False
        ),
        sa.Column("result_type", sa.String(length=100), nullable=False),
        sa.Column(
            "result_payload",
            postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("result_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=True),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("resource_version", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(result_type = 'completion' AND result_payload IS NULL AND resource_type IS NULL AND resource_id IS NULL AND resource_version IS NULL) OR (result_type <> 'completion' AND (result_payload IS NOT NULL OR (resource_type IS NOT NULL AND resource_id IS NOT NULL)))",
            name="ck_idempotency_records_replayable_result",
        ),
        sa.CheckConstraint(
            "(resource_type IS NULL AND resource_id IS NULL) OR (resource_type IS NOT NULL AND resource_id IS NOT NULL)",
            name="ck_idempotency_records_resource_pair",
        ),
        sa.CheckConstraint(
            "completed_at >= created_at", name="ck_idempotency_records_completion_time"
        ),
        sa.CheckConstraint(
            "expires_at > completed_at", name="ck_idempotency_records_expiration"
        ),
        sa.CheckConstraint(
            "fingerprint_version > 0", name="ck_idempotency_records_fingerprint_version"
        ),
        sa.CheckConstraint(
            "octet_length(key_digest) = 32",
            name="ck_idempotency_records_key_digest_sha256",
        ),
        sa.CheckConstraint(
            "octet_length(request_fingerprint) = 32",
            name="ck_idempotency_records_request_fingerprint_sha256",
        ),
        sa.CheckConstraint(
            "resource_version IS NULL OR (resource_type IS NOT NULL AND resource_id IS NOT NULL AND resource_version > 0)",
            name="ck_idempotency_records_resource_version",
        ),
        sa.CheckConstraint(
            "result_version > 0", name="ck_idempotency_records_result_version"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subject_id",
            "operation",
            "key_digest",
            name="uq_idempotency_records_identity",
        ),
    )
    op.create_index(
        "ix_idempotency_records_expires_at",
        "idempotency_records",
        ["expires_at", "id"],
        unique=False,
    )
    op.create_table(
        "profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=32), nullable=True),
        sa.Column("display_name", sa.String(length=64), nullable=False),
        sa.Column("bio", sa.String(length=255), nullable=True),
        sa.Column("avatar_key", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DISABLED', 'BLOCKED')", name="ck_profiles_status"
        ),
        sa.CheckConstraint(
            "username IS NULL OR username ~ '^[a-z0-9_]{3,32}$'",
            name="ck_profiles_username",
        ),
        sa.CheckConstraint(
            "bio IS NULL OR (length(bio) <= 255 AND position(chr(10) in bio) = 0 AND position(chr(13) in bio) = 0)",
            name="ck_profiles_bio",
        ),
        sa.CheckConstraint(
            "length(btrim(display_name)) BETWEEN 1 AND 64",
            name="ck_profiles_display_name",
        ),
        sa.CheckConstraint(
            "updated_at IS NULL OR updated_at > created_at",
            name="ck_profiles_timestamps",
        ),
        sa.CheckConstraint("version > 0", name="ck_profiles_version"),
        sa.PrimaryKeyConstraint("user_id", name="profiles_pkey"),
        sa.UniqueConstraint("username", name="profiles_username_key"),
    )
    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("theme", sa.String(length=6), nullable=False),
        sa.Column("locale", sa.String(length=2), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("privacy", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("locale IN ('ru', 'en')", name="ck_settings_locale"),
        sa.CheckConstraint(
            "theme IN ('light', 'dark', 'system')", name="ck_settings_theme"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(privacy) = 'object' AND privacy ?& ARRAY['who_can_see_avatar', 'who_can_find_by_username', 'who_can_see_bio'] AND privacy - ARRAY['who_can_see_avatar', 'who_can_find_by_username', 'who_can_see_bio'] = '{}'::jsonb AND privacy->>'who_can_see_avatar' IN ('ALL', 'NOBODY') AND privacy->>'who_can_find_by_username' IN ('ALL', 'NOBODY') AND privacy->>'who_can_see_bio' IN ('ALL', 'NOBODY') AND NOT privacy @> '{\"who_can_see_avatar\": null}'::jsonb AND NOT privacy @> '{\"who_can_find_by_username\": null}'::jsonb AND NOT privacy @> '{\"who_can_see_bio\": null}'::jsonb",
            name="ck_settings_privacy",
        ),
        sa.CheckConstraint(
            "updated_at IS NULL OR updated_at > created_at",
            name="ck_user_settings_timestamps",
        ),
        sa.CheckConstraint("version > 0", name="ck_user_settings_version"),
        sa.PrimaryKeyConstraint("user_id", name="user_settings_pkey"),
    )


def downgrade() -> None:
    op.drop_table("user_settings")
    op.drop_table("profiles")
    op.drop_index("ix_idempotency_records_expires_at", table_name="idempotency_records")
    op.drop_table("idempotency_records")

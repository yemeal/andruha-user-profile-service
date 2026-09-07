from pydantic import AliasChoices, Field

from app.core.settings.base import BaseContextSettings


class IdempotencySettings(BaseContextSettings):
    lease_seconds: int = Field(
        default=30,
        gt=0,
        validation_alias=AliasChoices(
            "PROFILE_IDEMPOTENCY_LEASE_SECONDS",
            "IDEMPOTENCY_LEASE_SECONDS",
            "lease_seconds",
        ),
    )
    result_ttl_seconds: int = Field(
        default=86400,
        gt=0,
        validation_alias=AliasChoices(
            "PROFILE_IDEMPOTENCY_RESULT_TTL_SECONDS",
            "IDEMPOTENCY_RESULT_TTL_SECONDS",
            "result_ttl_seconds",
        ),
    )
    cb_failures: int = Field(
        default=3,
        gt=0,
        validation_alias=AliasChoices(
            "PROFILE_IDEMPOTENCY_CB_FAILURES",
            "IDEMPOTENCY_CB_FAILURES",
            "cb_failures",
        ),
    )
    cb_recovery_seconds: float = Field(
        default=10.0,
        gt=0,
        validation_alias=AliasChoices(
            "PROFILE_IDEMPOTENCY_CB_RECOVERY_SECONDS",
            "IDEMPOTENCY_CB_RECOVERY_SECONDS",
            "cb_recovery_seconds",
        ),
    )

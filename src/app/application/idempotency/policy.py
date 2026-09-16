from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IdempotencyMode(StrEnum):
    HOT_ONLY = "HOT_ONLY"
    HOT_DURABLE = "HOT_DURABLE"


class IdempotencyPolicy(BaseModel):
    """Lease управляет владением, retention — сроком памяти результата."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: IdempotencyMode = IdempotencyMode.HOT_DURABLE
    lease_seconds: int = Field(default=30, gt=0)
    retention_seconds: int = Field(default=86400, gt=0)
    hot_cache_seconds: int = Field(default=300, gt=0)

    @model_validator(mode="after")
    def validate_cache_window(self) -> IdempotencyPolicy:
        if (
            self.mode is IdempotencyMode.HOT_DURABLE
            and self.hot_cache_seconds > self.retention_seconds
        ):
            raise ValueError(
                "hot_cache_seconds must not exceed durable retention_seconds"
            )
        return self

    @property
    def hot_result_ttl_seconds(self) -> int:
        if self.mode is IdempotencyMode.HOT_ONLY:
            return self.retention_seconds
        return self.hot_cache_seconds

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from app.application.idempotency.models import (
        ClaimResult,
        CompletedIdempotencyResult,
        IdempotencyKey,
    )


class HotIdempotencyStore(Protocol):
    """Порт volatile lease и replay; не зависит от конкретного хранилища."""

    async def claim(
        self,
        identity: IdempotencyKey,
        request_fingerprint: bytes,
        lease_token: UUID,
        lease_seconds: int,
    ) -> ClaimResult:
        """Попытка захвата распределенной блокировки для ключа."""
        ...

    async def renew(
        self,
        identity: IdempotencyKey,
        lease_token: UUID,
        lease_seconds: int,
    ) -> bool:
        """Продление срока действия распределенной блокировки (heartbeat)."""
        ...

    async def complete(
        self,
        identity: IdempotencyKey,
        lease_token: UUID,
        result: CompletedIdempotencyResult,
        *,
        cache_ttl_seconds: int,
    ) -> bool:
        """Публикует только под своим lease, не дольше cache TTL и expires_at.

        Возвращает False при потере владения или истёкшем результате.
        """
        ...

    async def release(
        self,
        identity: IdempotencyKey,
        lease_token: UUID,
    ) -> bool:
        """Досрочное освобождение блокировки при сбое операции."""
        ...

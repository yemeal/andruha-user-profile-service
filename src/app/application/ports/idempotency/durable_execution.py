from collections.abc import Awaitable, Callable
from typing import Protocol

from app.application.idempotency.models import (
    IdempotencyKey,
    IdempotencyResult,
    StoredResult,
)

IdempotentOperation = Callable[[], Awaitable[StoredResult]]


class DurableExecution(Protocol):
    """Atomic execution capability, independent of a database driver.

    Implementations must commit the local business effect and its replay record
    atomically, and roll back a losing attempt before returning the winner.
    A result store alone cannot provide this guarantee.
    """

    async def find_existing(
        self, identity: IdempotencyKey, request_fingerprint: bytes
    ) -> IdempotencyResult | None: ...

    async def execute_once(
        self,
        identity: IdempotencyKey,
        request_fingerprint: bytes,
        operation: IdempotentOperation,
        *,
        retention_seconds: int,
    ) -> IdempotencyResult: ...

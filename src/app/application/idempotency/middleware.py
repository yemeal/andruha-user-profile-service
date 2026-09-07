from app.application.exceptions.idempotency import (
    IdempotencyKeyRequiredError,
    IdempotencyScopeRequiredError,
)
from app.application.idempotency.coordinator import IdempotencyCoordinator
from app.application.idempotency.fingerprint import compute_key_digest
from app.application.idempotency.models import (
    CompletedIdempotencyResult,
    IdempotencyKey,
)
from app.application.idempotency.policy import IdempotencyPolicy
from app.application.ports.idempotency.durable_execution import IdempotentOperation


class IdempotencyMiddleware:
    """Оборачивает callback защитой от повторов и возвращает сохранённый результат.

    Не знает command, handler, CommandContext или ResultMode. Вызывающий код
    передаёт идентичность запроса и выбирает представление результата сам.
    """

    def __init__(self, coordinator: IdempotencyCoordinator) -> None:
        self._coordinator = coordinator

    async def execute(
        self,
        operation: IdempotentOperation,
        *,
        key: str | None,
        scope: str | None,
        operation_name: str,
        request_fingerprint: bytes,
        policy: IdempotencyPolicy,
    ) -> CompletedIdempotencyResult:
        if not key:
            raise IdempotencyKeyRequiredError("Idempotency key is required")
        if not scope:
            raise IdempotencyScopeRequiredError("Trusted idempotency scope is required")
        identity = IdempotencyKey(
            subject_id=scope,
            operation=operation_name,
            key_digest=compute_key_digest(key),
        )
        return await self._coordinator.execute(
            identity,
            request_fingerprint,
            operation,
            policy=policy,
        )

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel

from app.application.dispatching.context import CommandContext
from app.application.idempotency.coordinator import IdempotencyCoordinator
from app.application.idempotency.fingerprint import (
    compute_key_digest,
    compute_request_fingerprint,
)
from app.application.idempotency.models import (
    IdempotencyKey,
    StoredResult,
)
from app.application.idempotency.policy import IdempotencyPolicy


class IdempotencyMiddleware:
    """
    Единая точка интеграции CommandBus с подсистемой оркестрации идемпотентности.

    Перехватывает вызов идемпотентных команд, формирует изолированный ключ идемпотентности,
    вычисляет слепок запроса, координирует выполнение через IdempotencyCoordinator и
    прозрачно восстанавливает результат выполнения для вызывающего кода.
    """

    def __init__(self, coordinator: IdempotencyCoordinator) -> None:
        self._coordinator = coordinator

    @property
    def coordinator(self) -> IdempotencyCoordinator:
        """Ссылка на координатор идемпотентности."""
        return self._coordinator

    def supports_policy(self, policy: IdempotencyPolicy) -> bool:
        """Проверка поддержки заданной политики текущей конфигурацией."""
        return self._coordinator.supports_policy(policy)

    async def execute[CommandT: BaseModel, ResultT](
        self,
        command: CommandT,
        context: CommandContext,
        handler: Callable[[CommandT], Awaitable[ResultT]],
        *,
        policy: IdempotencyPolicy,
    ) -> ResultT:
        """Выполнение команды с соблюдением контракта идемпотентности."""
        if not context.idempotency_key:
            raise ValueError(
                "idempotency_key обязателен для выполнения идемпотентной команды"
            )

        key_digest = compute_key_digest(context.idempotency_key)
        subject_id = (
            context.actor_id
            or getattr(command, "user_id", None)
            or getattr(command, "subject_id", None)
            or "anonymous"
        )
        operation_name = (
            getattr(command, "operation_name", None) or type(command).__name__
        )

        identity = IdempotencyKey(
            subject_id=str(subject_id),
            operation=str(operation_name),
            key_digest=key_digest,
        )
        request_fingerprint = compute_request_fingerprint(command)

        captured_result: dict[str, Any] = {}

        async def _operation() -> StoredResult:
            res = await handler(command)
            captured_result["raw"] = res
            return self._serialize_result(res)

        completed = await self._coordinator.execute(
            identity,
            request_fingerprint,
            _operation,
            policy=policy,
        )

        if "raw" in captured_result:
            return captured_result["raw"]

        return self._deserialize_result(completed)

    @staticmethod
    def _serialize_result(result: Any) -> StoredResult:
        """Сериализация произвольного результата хендлера в структуру StoredResult."""
        if isinstance(result, StoredResult):
            return result
        if isinstance(result, BaseModel):
            resource_id = getattr(result, "id", None) or getattr(
                result, "user_id", None
            )
            resource_version = getattr(result, "version", None) or getattr(
                result, "expected_version", None
            )
            has_version = isinstance(resource_version, int) and resource_version > 0
            return StoredResult(
                result_type=type(result).__name__,
                result_payload=result.model_dump(mode="python"),
                result_version=1,
                resource_type=(
                    type(result).__name__ if resource_id is not None else None
                ),
                resource_id=str(resource_id) if resource_id is not None else None,
                resource_version=(
                    resource_version
                    if (resource_id is not None and has_version)
                    else None
                ),
            )
        if isinstance(result, dict):
            return StoredResult(
                result_type="dict",
                result_payload=result,
                result_version=1,
            )
        if result is None:
            return StoredResult(
                result_type="empty",
                result_payload={"_empty": True},
                result_version=1,
            )
        return StoredResult(
            result_type=type(result).__name__,
            result_payload={"value": result},
            result_version=1,
        )

    @staticmethod
    def _deserialize_result(stored: StoredResult) -> Any:
        """Восстановление структуры данных из StoredResult."""
        if stored.result_type == "empty":
            return None
        if stored.result_type == "dict":
            return stored.result_payload
        if stored.result_payload is not None:
            if "_empty" in stored.result_payload and len(stored.result_payload) == 1:
                return None
            if "value" in stored.result_payload and len(stored.result_payload) == 1:
                return stored.result_payload["value"]
            return stored.result_payload
        return stored

from collections.abc import Awaitable, Callable
from typing import Any

from app.application.commands.base import BaseCommand
from app.application.dispatching.context import CommandContext
from app.application.dispatching.registry import CommandHandlerRegistration
from app.application.dispatching.result_mode import ResultMode
from app.application.idempotency.fingerprint import compute_request_fingerprint
from app.application.idempotency.middleware import IdempotencyMiddleware
from app.application.idempotency.models import StoredResult
from app.application.idempotency.policy import IdempotencyMode
from app.application.ports.persistence.unit_of_work import AsyncUOWProtocol


class CommandExecution[DependenciesT]:
    """Выполнение одной команды с зависимостями текущего dispatch.

    Handler получает обычные application-зависимости. Выбор владельца
    транзакции сосредоточен здесь и не попадает в CommandBus или handler.
    """

    def __init__(
        self,
        dependencies: DependenciesT,
        uow: AsyncUOWProtocol,
        idempotency: IdempotencyMiddleware,
    ) -> None:
        self._dependencies = dependencies
        self._uow = uow
        self._idempotency = idempotency

    async def execute[CommandT: BaseCommand[Any], ResultT](
        self,
        registration: CommandHandlerRegistration[DependenciesT, CommandT, ResultT],
        command: CommandT,
        context: CommandContext,
        *,
        result_mode: ResultMode = ResultMode.REPLAYABLE,
    ) -> ResultT | None:
        # Отложенный вызов: на replay обёртка не создаёт даже handler.
        async def invoke_handler() -> StoredResult:
            handler = registration.handler_factory(self._dependencies)
            result = await handler(command)
            if result_mode is ResultMode.COMPLETION_ONLY:
                # Контракт handler проверяется до commit даже без snapshot.
                # Сам DTO не сериализуем и не передаём в storage.
                registration.codec.validate(result)
                return StoredResult.completion()
            return registration.codec.encode(result)

        async def run_transaction() -> StoredResult:
            async with self._uow:
                return await invoke_handler()

        policy = registration.idempotency_policy
        if policy is None:
            stored = await run_transaction()
        else:
            # HOT_ONLY: оборачиваем callback вместе с бизнес-транзакцией.
            # HOT_DURABLE: обёртка включает callback и replay в общую транзакцию.
            operation: Callable[[], Awaitable[StoredResult]] = (
                run_transaction
                if policy.mode is IdempotencyMode.HOT_ONLY
                else invoke_handler
            )
            stored = await self._idempotency.execute(
                operation,
                key=context.idempotency_key,
                scope=context.idempotency_scope,
                operation_name=registration.operation,
                request_fingerprint=compute_request_fingerprint(command),
                policy=policy,
            )

        # Единый выход для первого выполнения, replay и команды без policy.
        if result_mode is ResultMode.COMPLETION_ONLY:
            return None
        return registration.codec.decode(stored)

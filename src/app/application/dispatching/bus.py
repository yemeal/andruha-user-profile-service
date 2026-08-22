from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from app.application.commands.base import BaseCommand
from app.application.dispatching.context import CommandContext
from app.application.dispatching.registry import CommandHandlerRegistry
from app.application.exceptions.idempotency import IdempotencyKeyRequiredError

if TYPE_CHECKING:
    from app.application.idempotency.middleware import IdempotencyMiddleware


class CommandBusProtocol(Protocol):
    """
    Публичный контракт шины команд.

    Предоставляет вызывающему коду (контроллерам, слушателям событий)
    единственный метод dispatch() для выполнения команд.
    """

    async def dispatch[ResultT](
        self,
        command: BaseCommand[ResultT],
        context: CommandContext | None = None,
    ) -> ResultT: ...


class CommandBus:
    """
    Диспетчер команд прикладного слоя.

    Предоставляет вызывающему коду единственный метод dispatch(), сопоставляет
    команду с зарегистрированным обработчиком из CommandHandlerRegistry и маршрутизирует
    выполнение через IdempotencyMiddleware, если это необходимо.
    """

    def __init__(
        self,
        registry: CommandHandlerRegistry,
        idempotency_middleware: IdempotencyMiddleware | None = None,
    ) -> None:
        self._registry = registry
        self._middleware = idempotency_middleware
        self._validate_configuration()

    def _validate_configuration(self) -> None:
        """
        Fail-Fast проверка согласованности конфигурации команд и middleware при старте приложения.
        """
        for command_type, registration in self._registry.registrations.items():
            policy = registration.idempotency_policy
            if policy is None:
                continue

            if self._middleware is None:
                raise RuntimeError(
                    f"Ошибка конфигурации: для команды '{command_type.__name__}' задана политика "
                    + "идемпотентности, но IdempotencyMiddleware не передан в CommandBus"
                )

            if not self._middleware.supports_policy(policy):
                raise RuntimeError(
                    f"Ошибка конфигурации: команда '{command_type.__name__}' требует режим {policy.mode}, "
                    + "но долговечное хранилище (durable_execution) не настроено в IdempotencyCoordinator"
                )

    async def dispatch[ResultT](
        self,
        command: BaseCommand[ResultT],
        context: CommandContext | None = None,
    ) -> ResultT:
        # Ищем регистрацию обработчика для команды
        command_type = type(command)
        registration = self._registry.get(command_type)
        if registration is None:
            raise KeyError(
                f"Не зарегистрирован обработчик для команды {command_type.__name__}"
            )

        # Смотрим, настроена ли политика идемпотентности для данной команды
        policy = registration.idempotency_policy
        if policy is None:
            # Если политики идемпотентности нет - выполняем команду напрямую и возвращаем результат
            return await registration.handler(command)

        if context is None:
            context = CommandContext()

        if not context.idempotency_key:
            raise IdempotencyKeyRequiredError(
                f"Ключ идемпотентности обязателен для команды '{command_type.__name__}'"
            )

        if self._middleware is None:
            raise RuntimeError(
                "Для выполнения идемпотентных команд требуется настроить IdempotencyMiddleware"
            )

        return await self._middleware.execute(
            command,
            context,
            registration.handler,
            policy=policy,
        )

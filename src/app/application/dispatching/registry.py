from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from app.application.commands.base import BaseCommand
from app.application.idempotency.codec import PydanticResultCodec
from app.application.idempotency.policy import IdempotencyPolicy
from app.application.ports.idempotency.result_codec import IdempotencyResultCodec

type CommandHandler[CommandT, ResultT] = Callable[[CommandT], Awaitable[ResultT]]


@dataclass(frozen=True, slots=True)
class CommandHandlerRegistration[DependenciesT, CommandT, ResultT]:
    """Проверенный контракт команды; handler будет создан в scope текущего dispatch."""

    handler_factory: Callable[[DependenciesT], CommandHandler[CommandT, ResultT]]
    codec: IdempotencyResultCodec[ResultT]
    operation: str
    idempotency_policy: IdempotencyPolicy | None


class CommandHandlerRegistry[DependenciesT]:
    """Изменяется только при сборке. После freeze новые регистрации запрещены."""

    def __init__(self) -> None:
        # Any ограничен гетерогенным индексом; типизированный контракт задаётся register.
        self._handlers: dict[
            type[BaseCommand[Any]], CommandHandlerRegistration[DependenciesT, Any, Any]
        ] = {}
        self._frozen = False

    def register[CommandT: BaseCommand[Any], ResultT](
        self,
        command_cls: type[CommandT],
        handler_factory: Callable[[DependenciesT], CommandHandler[CommandT, ResultT]],
        *,
        result_type: type[ResultT],
        operation: str,
        idempotency_policy: IdempotencyPolicy | None = None,
        result_schema_version: int = 1,
    ) -> None:
        if self._frozen:
            raise RuntimeError("Command registry is frozen")
        if command_cls in self._handlers:
            raise ValueError(f"Command already registered: {command_cls.__name__}")
        if not issubclass(command_cls, BaseCommand):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("command_cls must inherit BaseCommand")
        if not operation.strip() or len(operation) > 100:
            raise ValueError("operation must contain 1..100 non-blank characters")
        if any(item.operation == operation for item in self._handlers.values()):
            raise ValueError(f"Operation already registered: {operation}")
        if not callable(handler_factory):
            raise TypeError("handler_factory must be callable")
        if result_type is Any:  # pyright: ignore[reportUnnecessaryComparison]
            raise TypeError("A concrete result schema is required")
        codec = PydanticResultCodec(result_type, schema_version=result_schema_version)
        self._handlers[command_cls] = CommandHandlerRegistration(
            handler_factory=handler_factory,
            codec=codec,
            operation=operation,
            idempotency_policy=idempotency_policy,
        )

    def freeze(
        self,
    ) -> Mapping[
        type[BaseCommand[Any]], CommandHandlerRegistration[DependenciesT, Any, Any]
    ]:
        self._frozen = True
        return MappingProxyType(dict(self._handlers))

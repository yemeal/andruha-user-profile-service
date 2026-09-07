from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Literal, Protocol, overload

from app.application.commands.base import BaseCommand
from app.application.dispatching.context import CommandContext
from app.application.dispatching.execution import CommandExecution
from app.application.dispatching.registry import CommandHandlerRegistry
from app.application.dispatching.result_mode import ResultMode


class CommandBusProtocol(Protocol):
    @overload
    async def dispatch[ResultT](
        self,
        command: BaseCommand[ResultT],
        context: CommandContext | None = None,
        *,
        result_mode: Literal[ResultMode.REPLAYABLE] = ResultMode.REPLAYABLE,
    ) -> ResultT: ...

    @overload
    async def dispatch[ResultT](
        self,
        command: BaseCommand[ResultT],
        context: CommandContext | None = None,
        *,
        result_mode: Literal[ResultMode.COMPLETION_ONLY],
    ) -> None: ...

    @overload
    async def dispatch[ResultT](
        self,
        command: BaseCommand[ResultT],
        context: CommandContext | None = None,
        *,
        result_mode: ResultMode,
    ) -> ResultT | None: ...


class CommandBus[DependenciesT]:
    """Маршрутизация и отдельный scope на каждый dispatch.

    ResultMode определяет контракт ответа; его реализация находится в execution.
    """

    def __init__(
        self,
        registry: CommandHandlerRegistry[DependenciesT],
        scope_factory: Callable[
            [], AbstractAsyncContextManager[CommandExecution[DependenciesT]]
        ],
    ) -> None:
        self._handlers = registry.freeze()
        self._scope_factory = scope_factory

    @overload
    async def dispatch[ResultT](
        self,
        command: BaseCommand[ResultT],
        context: CommandContext | None = None,
        *,
        result_mode: Literal[ResultMode.REPLAYABLE] = ResultMode.REPLAYABLE,
    ) -> ResultT: ...

    @overload
    async def dispatch[ResultT](
        self,
        command: BaseCommand[ResultT],
        context: CommandContext | None = None,
        *,
        result_mode: Literal[ResultMode.COMPLETION_ONLY],
    ) -> None: ...

    @overload
    async def dispatch[ResultT](
        self,
        command: BaseCommand[ResultT],
        context: CommandContext | None = None,
        *,
        result_mode: ResultMode,
    ) -> ResultT | None: ...

    async def dispatch[ResultT](
        self,
        command: BaseCommand[ResultT],
        context: CommandContext | None = None,
        *,
        result_mode: ResultMode = ResultMode.REPLAYABLE,
    ) -> ResultT | None:
        if not isinstance(result_mode, ResultMode):
            raise TypeError("result_mode must be a ResultMode")
        registration = self._handlers.get(type(command))
        if registration is None:
            raise KeyError(f"Command not registered: {type(command).__name__}")
        async with self._scope_factory() as execution:
            return await execution.execute(
                registration,
                command,
                context or CommandContext(),
                result_mode=result_mode,
            )

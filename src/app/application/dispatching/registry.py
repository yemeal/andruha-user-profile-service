from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.application.commands.base import BaseCommand
from app.application.idempotency.policy import IdempotencyPolicy

CommandHandler = Callable[[Any], Awaitable[Any]]


class CommandHandlerRegistration(BaseModel):
    """Регистрационная запись обработчика команды и связанной политики идемпотентности."""

    model_config = ConfigDict(
        frozen=True,
        arbitrary_types_allowed=True,
        extra="forbid",
    )

    handler: CommandHandler
    idempotency_policy: IdempotencyPolicy | None = None


class CommandHandlerRegistry:
    """
    Реестр сопоставления команд и их обработчиков.

    Используется исключительно на этапе инициализации приложения (Composition Root / DI).
    """

    def __init__(self) -> None:
        self._handlers: dict[type[BaseModel], CommandHandlerRegistration] = {}

    def register[ResultT, CommandT: BaseCommand[Any]](
        self,
        command_cls: type[CommandT],
        handler: Callable[[CommandT], Awaitable[ResultT]],
        idempotency_policy: IdempotencyPolicy | None = None,
    ) -> None:
        """Регистрация обработчика и опциональной политики идемпотентности для типа команды."""
        if command_cls in self._handlers:
            raise ValueError(
                f"Обработчик для команды {command_cls.__name__} уже зарегистрирован"
            )
        self._handlers[command_cls] = CommandHandlerRegistration(
            handler=handler,
            idempotency_policy=idempotency_policy,
        )

    def get(self, command_type: type[BaseModel]) -> CommandHandlerRegistration | None:
        """Получение регистрации обработчика по типу команды."""
        return self._handlers.get(command_type)

    @property
    def registrations(self) -> dict[type[BaseModel], CommandHandlerRegistration]:
        """Все зарегистрированные обработчики и их политики идемпотентности."""
        return dict(self._handlers)

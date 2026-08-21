from types import TracebackType
from typing import Protocol, Self


class AsyncUOWProtocol(Protocol):
    """
    Атомарная транзакционная граница (Unit of Work).
    Управляет жизненным циклом транзакции через асинхронный контекстный менеджер:

    - Автоматически фиксирует (commit) транзакцию при успешном завершении блока.
    - Автоматически откатывает (rollback) транзакцию при возникновении исключения.
    """

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None: ...

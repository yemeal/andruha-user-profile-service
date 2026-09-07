"""Исключения инфраструктурного слоя базы данных."""


class DatabaseError(Exception):
    """Базовое исключение слоя базы данных."""


class TransactionError(DatabaseError, RuntimeError):
    """Базовое исключение для ошибок транзакционного контекста."""


class TransactionRequiredError(TransactionError):
    """Операция БД вызвана без активной транзакции (Unit of Work)."""

    def __init__(
        self, message: str = "Repository requires an explicit transaction/UoW"
    ) -> None:
        super().__init__(message)


class NestedTransactionNotAllowedError(TransactionError):
    """Попытка открыть вложенную или разделяемую транзакцию в Unit of Work."""

    def __init__(
        self, message: str = "Nested or shared UoW transaction is not allowed"
    ) -> None:
        super().__init__(message)


class TransactionNotStartedError(TransactionError):
    """Попытка завершить транзакцию Unit of Work, которая не была запущена."""

    def __init__(self, message: str = "UoW transaction has not been started") -> None:
        super().__init__(message)

class IdempotencyError(Exception):
    """Базовое исключение подсистемы оркестрации идемпотентности."""


class IdempotencyKeyRequiredError(IdempotencyError):
    """Ключ идемпотентности строго обязателен для команды, но не был передан в контексте."""


class IdempotencyUnavailableError(IdempotencyError):
    """Защита идемпотентности недоступна; после запуска операции её эффект уже мог произойти."""


class IdempotencyConflictError(IdempotencyError):
    """Ключ идемпотентности повторно использован с отличающимся телом/слепком запроса."""


class IdempotencyInProgressError(IdempotencyError):
    """Параллельный запрос с данным ключом идемпотентности уже находится в процессе обработки."""


class StoredReplayUnavailableError(IdempotencyError):
    """Сохраненный результат невозможно десериализовать, расшифровать или восстановить."""


class IdempotencyScopeRequiredError(IdempotencyError):
    """Для команды отсутствует доверенный scope идемпотентности."""


class IdempotencyResultNotStoredError(IdempotencyError):
    """Операция выполнена, но её результат намеренно не сохранён.

    Повторное выполнение handler для получения результата запрещено.
    """

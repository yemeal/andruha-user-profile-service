class IdempotencyError(Exception):
    """Базовое исключение подсистемы оркестрации идемпотентности."""


class IdempotencyKeyRequiredError(IdempotencyError):
    """Ключ идемпотентности строго обязателен для команды, но не был передан в контексте."""


class IdempotencyUnavailableError(IdempotencyError):
    """Хранилище идемпотентности недоступно; операция прервана в режиме fail-closed."""


class IdempotencyConflictError(IdempotencyError):
    """Ключ идемпотентности повторно использован с отличающимся телом/слепком запроса."""


class IdempotencyInProgressError(IdempotencyError):
    """Параллельный запрос с данным ключом идемпотентности уже находится в процессе обработки."""


class StoredReplayUnavailableError(IdempotencyError):
    """Сохраненный результат невозможно десериализовать, расшифровать или восстановить."""

class TransactionConflictError(Exception):
    """A persistence adapter reports a rolled-back concurrency conflict.

    Map only documented retryable concurrency failures (for example,
    serialization failures), not every IntegrityError or DBAPIError.
    """


class PersistenceUnavailableError(Exception):
    """Хранилище недоступно; исход commit может быть неизвестен."""

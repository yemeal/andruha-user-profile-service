from typing import Protocol


class IdempotencyMetrics(Protocol):
    """Порт сбора метрик и телеметрии идемпотентности."""

    def observe_outcome(self, outcome: str) -> None:
        """Регистрация исхода выполнения операции (EXECUTED, REPLAY, CONFLICT, IN_PROGRESS)."""
        ...

    def observe_hot_degraded(self, stage: str) -> None:
        """Регистрация событий деградации горячего хранилища (begin, release, complete, lease)."""
        ...

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.application.idempotency.models import ExecutionStatus, HotDegradationStage


class IdempotencyMetrics(Protocol):
    """Порт сбора метрик и телеметрии идемпотентности."""

    def observe_outcome(self, outcome: ExecutionStatus) -> None:
        """Регистрация исхода выполнения операции (EXECUTED, REPLAY, CONFLICT, IN_PROGRESS)."""
        ...

    def observe_hot_degraded(self, stage: HotDegradationStage) -> None:
        """Регистрация событий деградации горячего хранилища (begin, release, complete, lease)."""
        ...

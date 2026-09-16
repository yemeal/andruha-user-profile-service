from enum import StrEnum


class ResultMode(StrEnum):
    """Контракт результата dispatch; не зависит от транспорта и режима хранения."""

    REPLAYABLE = "REPLAYABLE"
    COMPLETION_ONLY = "COMPLETION_ONLY"

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Возвращает текущее время в таймзоне UTC."""
    return datetime.now(UTC)

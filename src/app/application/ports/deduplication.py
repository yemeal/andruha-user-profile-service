from datetime import datetime
from typing import Protocol
from uuid import UUID


class EventDeduplicationPort(Protocol):
    """
    Порт дедупликации входящих событий (Inbox Fence).
    Используется для защиты от повторной обработки сообщений из брокера (Exactly-Once semantics).
    """

    async def mark_processed_if_absent(
        self,
        event_id: UUID,
        processed_at: datetime,
    ) -> bool:
        """
        Атомарно фиксирует факт обработки события в хранилище дедупликации.

        Возвращает:

        - True: если событие зарегистрировано впервые (первая доставка).
        - False: если событие с таким event_id уже обрабатывалось ранее (дубликат).
        """
        ...

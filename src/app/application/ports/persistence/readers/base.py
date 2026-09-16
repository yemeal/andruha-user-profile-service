from collections.abc import Sequence
from typing import Protocol


class AsyncReaderProtocol[EntityT, IdT](Protocol):
    """Базовый асинхронный протокол ридера (Read Side / Projections)."""

    async def get_by_id(self, entity_id: IdT) -> EntityT | None:
        """Получить сущность по первичному идентификатору."""
        ...

    async def get_batch(self, entity_ids: Sequence[IdT]) -> list[EntityT]:
        """Пакетное получение сущностей по списку идентификаторов."""
        ...

    async def exists(self, entity_id: IdT) -> bool:
        """Проверить факт существования сущности."""
        ...

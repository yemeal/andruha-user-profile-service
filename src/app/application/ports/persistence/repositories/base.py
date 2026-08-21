from typing import Protocol


class AsyncRepositoryProtocol[EntityT, IdT](Protocol):
    """
    Базовый асинхронный протокол репозитория с универсальным CRUD-контрактом.
    """

    async def create(self, entity: EntityT) -> EntityT:
        """
        Добавить новую сущность в хранилище.

        Может вызвать ошибку уникальности, если сущность уже существует.
        """
        ...

    async def get_by_id(self, entity_id: IdT) -> EntityT | None:
        """
        Получить сущность по первичному идентификатору.
        """
        ...

    async def update(
        self,
        entity: EntityT,
        *,
        expected_version: int | None = None,
    ) -> EntityT:
        """
        Обновить существующую сущность.

        Если передан expected_version, выполняет оптимистическую проверку версии (OCC)
        и выбрасывает исключение конфликта версий при несовпадении.
        """
        ...

    async def delete(self, entity_id: IdT) -> bool:
        """
        Удалить сущность по первичному идентификатору.

        Возвращает True, если запись была удалена, и False, если не существовала.
        """
        ...

    async def exists(self, entity_id: IdT) -> bool:
        """
        Проверить факт существования сущности в хранилище.
        """
        ...

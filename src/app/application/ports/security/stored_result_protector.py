from typing import Any, Protocol

from pydantic import JsonValue


class StoredResultProtector(Protocol):
    """Порт шифрования и защиты конфиденциальных результатов перед сохранением."""

    def protect(self, payload: dict[str, JsonValue], *, aad: bytes) -> dict[str, Any]:
        """Шифрование полезной нагрузки с аутентификационными данными (AAD)."""
        ...

    def restore(self, envelope: dict[str, Any], *, aad: bytes) -> dict[str, JsonValue]:
        """Расшифровка и верификация конверта с результатом."""
        ...

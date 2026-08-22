from typing import Any, Protocol


class StoredResultProtector(Protocol):
    """Порт шифрования и защиты конфиденциальных результатов перед сохранением."""

    def protect(self, payload: dict[str, str], *, aad: bytes) -> dict[str, Any]:
        """Шифрование полезной нагрузки с аутентификационными данными (AAD)."""
        ...

    def restore(self, envelope: dict[str, Any], *, aad: bytes) -> dict[str, str]:
        """Расшифровка и верификация конверта с результатом."""
        ...

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence, Set
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel

JsonPath = tuple[str, ...]


def compute_key_digest(raw_key: str) -> bytes:
    """Хэширование клиентского ключа идемпотентности в 32-байтный SHA-256 дайджест."""
    if not raw_key:
        raise ValueError("Ключ идемпотентности не может быть пустым")
    return hashlib.sha256(raw_key.encode("utf-8")).digest()


def compute_request_fingerprint(
    payload: Mapping[str, Any] | BaseModel,
    *,
    unordered_paths: Set[JsonPath] | None = None,
) -> bytes:
    """
    Построение детерминированного 32-байтного SHA-256 слепка семантического тела запроса.

    Канонизирует словари, последовательности, множества, Decimal, даты, UUID и Enum.
    Пути к неупорядоченным коллекциям сортируются нечувствительно к порядку элементов.
    """
    effective_paths = unordered_paths if unordered_paths is not None else frozenset()
    raw = (
        payload.model_dump(mode="python") if isinstance(payload, BaseModel) else payload
    )
    canonical = _canonicalize(raw, path=(), unordered_paths=effective_paths)
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).digest()


def _canonicalize(
    value: Any,
    *,
    path: JsonPath,
    unordered_paths: Set[JsonPath],
) -> Any:
    if isinstance(value, BaseModel):
        return _canonicalize(
            value.model_dump(mode="python"),
            path=path,
            unordered_paths=unordered_paths,
        )
    if isinstance(value, Mapping):
        for key in value:
            if not isinstance(key, str):
                raise TypeError(
                    "Словари для формирования слепка должны содержать строковые ключи"
                )
        return {
            key: _canonicalize(
                item,
                path=(*path, key),
                unordered_paths=unordered_paths,
            )
            for key, item in sorted(value.items())
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = [
            _canonicalize(
                item,
                path=(*path, "[]"),
                unordered_paths=unordered_paths,
            )
            for item in value
        ]
        if path in unordered_paths:
            return sorted(
                items,
                key=lambda item: json.dumps(
                    item,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
        return items
    if isinstance(value, Set):
        items = [
            _canonicalize(item, path=(*path, "{}"), unordered_paths=unordered_paths)
            for item in value
        ]
        return sorted(
            items,
            key=lambda item: json.dumps(
                item,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(
                "Значения Decimal для слепка должны быть конечными числами"
            )
        if value == 0:
            return "0"
        return format(value.normalize(), "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError(
                "Значения datetime для слепка должны содержать часовой пояс (timezone-aware)"
            )
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return _canonicalize(
            value.value,
            path=path,
            unordered_paths=unordered_paths,
        )
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Значения float для слепка должны быть конечными числами")
        return value if value else 0.0
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"Неподдерживаемый тип значения для слепка: {type(value).__name__}")

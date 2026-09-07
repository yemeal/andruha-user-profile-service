from typing import Protocol

from app.application.idempotency.models import StoredResult


class IdempotencyResultCodec[ResultT](Protocol):
    """Тип результата и версия схемы фиксируются один раз при сборке."""

    def validate(self, result: ResultT) -> ResultT: ...
    def encode(self, result: ResultT) -> StoredResult: ...
    def decode(self, stored: StoredResult) -> ResultT: ...

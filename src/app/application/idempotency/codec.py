from pydantic import BaseModel, TypeAdapter

from app.application.exceptions.idempotency import (
    IdempotencyResultNotStoredError,
    StoredReplayUnavailableError,
)
from app.application.idempotency.models import StoredResult


class PydanticResultCodec[ResultT]:
    """Схема результата компилируется при регистрации, до первого dispatch."""

    def __init__(self, result_type: type[ResultT], *, schema_version: int = 1) -> None:
        if schema_version < 1:
            raise ValueError("schema_version must be positive")
        self._result_type = result_type
        self._adapter = TypeAdapter(result_type)
        self._schema_version = schema_version

    def validate(self, result: ResultT) -> ResultT:
        """Проверяет результат handler без JSON-сериализации."""
        validated = self._adapter.validate_python(result, strict=True)
        # Pydantic умеет построить DTO из dict даже в strict-режиме.
        # Хендлер обязан вернуть сам DTO; преобразование из JSON нужно только replay.
        if (
            isinstance(self._result_type, type)
            and issubclass(self._result_type, BaseModel)
            and not isinstance(result, self._result_type)
        ):
            raise TypeError(
                f"Handler must return an instance of {self._result_type.__name__}"
            )
        return validated

    def encode(self, result: ResultT) -> StoredResult:
        # Проверяем контракт до commit: ошибка handler не должна закрепиться в БД.
        validated = self.validate(result)
        return StoredResult(
            result_type="snapshot",
            result_payload={
                "value": self._adapter.dump_python(
                    validated, mode="json", warnings="error"
                )
            },
            result_version=self._schema_version,
        )

    def decode(self, stored: StoredResult) -> ResultT:
        if stored.is_completion_only:
            raise IdempotencyResultNotStoredError(
                "Operation completed successfully, but its result was not retained"
            )
        try:
            if stored.result_version != self._schema_version:
                raise ValueError("Unsupported stored result schema version")
            payload = stored.result_payload
            if payload is None or set(payload) != {"value"}:
                raise ValueError("A value snapshot is required")
            return self._adapter.validate_python(payload["value"])
        except (ValueError, TypeError, KeyError) as error:
            raise StoredReplayUnavailableError(
                "Stored result does not match the registered result schema"
            ) from error

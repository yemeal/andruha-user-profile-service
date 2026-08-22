from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CommandContext(BaseModel):
    """
    Контекст выполнения, сопровождающий отправку команды в шину.

    Содержит транспортно-независимые метаданные запроса (ключ идемпотентности,
    идентификатор актора, сквозной correlation ID).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    idempotency_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Клиентский ключ идемпотентности",
    )
    actor_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Идентификатор авторизованного пользователя/субъекта действия",
    )
    correlation_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Сквозной идентификатор трассировки распределенного запроса",
    )

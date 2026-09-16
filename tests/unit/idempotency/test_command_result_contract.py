import pytest
from fakes import State, build_bus
from pydantic import BaseModel, ValidationError

from app.application.commands.base import BaseCommand
from app.application.dispatching.context import CommandContext
from app.application.dispatching.registry import CommandHandlerRegistry
from app.application.dispatching.result_mode import ResultMode
from app.application.idempotency.policy import IdempotencyMode, IdempotencyPolicy


class Reply(BaseModel):
    value: str


class OtherReply(BaseModel):
    value: str


class Change(BaseCommand[Reply]):
    pass


@pytest.mark.parametrize("mode", list(ResultMode))
@pytest.mark.parametrize("storage_mode", [None, *IdempotencyMode])
@pytest.mark.parametrize(
    "bad_result", [None, {"value": "looks valid"}, OtherReply(value="wrong DTO")]
)
async def test_wrong_result_rolls_back_in_every_execution_mode(
    monkeypatch, mode, storage_mode, bad_result
):
    state, registry = State(), CommandHandlerRegistry()

    def factory(session):
        async def handler(command):
            session.stage("must rollback")
            return bad_result

        return handler

    registry.register(
        Change,
        factory,
        result_type=Reply,
        operation="change",
        idempotency_policy=IdempotencyPolicy(mode=storage_mode)
        if storage_mode
        else None,
    )
    bus = build_bus(monkeypatch, registry, state)
    with pytest.raises((TypeError, ValidationError)):
        await bus.dispatch(
            Change(),
            CommandContext(idempotency_key="key", idempotency_scope="user:1"),
            result_mode=mode,
        )
    assert not state.effects and not state.records and not state.hot

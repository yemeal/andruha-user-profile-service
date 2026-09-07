import asyncio
from types import NoneType

import pytest
from fakes import State, build_bus
from pydantic import BaseModel, ValidationError, field_serializer

from app.application.commands.base import BaseCommand
from app.application.dispatching.context import CommandContext
from app.application.dispatching.registry import CommandHandlerRegistry
from app.application.dispatching.result_mode import ResultMode
from app.application.exceptions.idempotency import (
    IdempotencyConflictError,
    IdempotencyResultNotStoredError,
)
from app.application.idempotency.codec import PydanticResultCodec
from app.application.idempotency.models import StoredResult
from app.application.idempotency.policy import IdempotencyMode, IdempotencyPolicy
from app.infrastructure.idempotency.redis.hot_store import RedisHotIdempotencyStore


class Reply(BaseModel):
    value: str


class Change(BaseCommand[Reply]):
    value: str


def context():
    return CommandContext(idempotency_key="same", idempotency_scope="subject:1")


def registry_with_handler(policy, calls):
    registry = CommandHandlerRegistry()

    def factory(session):
        async def handler(command):
            calls.append(session)
            session.stage(command.value)
            return Reply(value=command.value)

        return handler

    registry.register(
        Change,
        factory,
        result_type=Reply,
        operation="profile.change",
        idempotency_policy=policy,
    )
    return registry


@pytest.mark.parametrize("first_mode", list(ResultMode))
@pytest.mark.parametrize("repeat_mode", list(ResultMode))
@pytest.mark.parametrize("path", ["hot_only", "durable_hot", "durable_cold"])
async def test_result_modes_share_identity_and_preserve_first_completion(
    monkeypatch, first_mode, repeat_mode, path
):
    storage_mode = (
        IdempotencyMode.HOT_ONLY if path == "hot_only" else IdempotencyMode.HOT_DURABLE
    )
    state, calls = State(), []
    registry = registry_with_handler(IdempotencyPolicy(mode=storage_mode), calls)
    bus = build_bus(monkeypatch, registry, state)
    command = Change(value="original")
    first = await bus.dispatch(command, context(), result_mode=first_mode)
    assert first == (
        Reply(value="original") if first_mode is ResultMode.REPLAYABLE else None
    )
    record = next(iter(state.hot.values()))["result"]
    deadline = record.expires_at
    assert record.is_completion_only == (first_mode is ResultMode.COMPLETION_ONLY)
    assert record.result_payload == (
        {"value": {"value": "original"}}
        if first_mode is ResultMode.REPLAYABLE
        else None
    )
    if path == "durable_cold":
        state.hot.clear()

    if (
        first_mode is ResultMode.COMPLETION_ONLY
        and repeat_mode is ResultMode.REPLAYABLE
    ):
        with pytest.raises(IdempotencyResultNotStoredError):
            await bus.dispatch(command, context(), result_mode=repeat_mode)
    else:
        repeat = await bus.dispatch(command, context(), result_mode=repeat_mode)
        assert repeat == (
            Reply(value="original") if repeat_mode is ResultMode.REPLAYABLE else None
        )

    assert len(calls) == 1
    assert state.effects == ["original"]
    assert next(iter(state.hot.values()))["result"] == record
    assert next(iter(state.hot.values()))["result"].expires_at == deadline
    assert len(state.records) == (0 if path == "hot_only" else 1)


@pytest.mark.parametrize("storage_mode", list(IdempotencyMode))
async def test_completion_marker_still_rejects_a_different_command(
    monkeypatch, storage_mode
):
    state, calls = State(), []
    registry = registry_with_handler(IdempotencyPolicy(mode=storage_mode), calls)
    bus = build_bus(monkeypatch, registry, state)
    await bus.dispatch(
        Change(value="original"), context(), result_mode=ResultMode.COMPLETION_ONLY
    )
    with pytest.raises(IdempotencyConflictError):
        await bus.dispatch(
            Change(value="changed"), context(), result_mode=ResultMode.COMPLETION_ONLY
        )
    assert state.effects == ["original"]
    assert len(calls) == 1


async def test_completion_without_policy_returns_none_but_does_not_deduplicate(
    monkeypatch,
):
    state, calls = State(), []
    bus = build_bus(monkeypatch, registry_with_handler(None, calls), state)
    assert (
        await bus.dispatch(Change(value="x"), result_mode=ResultMode.COMPLETION_ONLY)
        is None
    )
    assert await bus.dispatch(Change(value="x")) == Reply(value="x")
    assert state.effects == ["x", "x"]
    assert not state.records and not state.hot


@pytest.mark.parametrize("storage_mode", [None, *IdempotencyMode])
async def test_completion_validates_result_but_never_serializes_large_payload(
    monkeypatch, storage_mode
):
    class UnserializableReply(BaseModel):
        value: str

        @field_serializer("value")
        def serialize_value(self, value):
            raise AssertionError("Completion must not serialize the handler result")

    class LargeCommand(BaseCommand[UnserializableReply]):
        pass

    state, registry = State(), CommandHandlerRegistry()

    def factory(session):
        async def handler(command):
            session.stage("written")
            return UnserializableReply(value="private-data" * 100_000)

        return handler

    registry.register(
        LargeCommand,
        factory,
        result_type=UnserializableReply,
        operation="large",
        idempotency_policy=IdempotencyPolicy(mode=storage_mode)
        if storage_mode
        else None,
    )
    bus = build_bus(monkeypatch, registry, state)
    assert (
        await bus.dispatch(
            LargeCommand(), context(), result_mode=ResultMode.COMPLETION_ONLY
        )
        is None
    )
    assert state.effects == ["written"]
    records = [
        *state.records.values(),
        *(entry["result"] for entry in state.hot.values()),
    ]
    for record in records:
        encoded = RedisHotIdempotencyStore._encode_completed(record)
        assert RedisHotIdempotencyStore._decode_completed(encoded) == record
        assert len(encoded) < 1000
        assert "private-data" not in encoded
        assert record.result_payload is None and record.is_completion_only


@pytest.mark.parametrize("storage_mode", [None, *IdempotencyMode])
async def test_completion_does_not_bypass_handler_result_validation(
    monkeypatch, storage_mode
):
    state, registry = State(), CommandHandlerRegistry()

    def factory(session):
        async def handler(command):
            session.stage("must rollback")
            return 123

        return handler

    registry.register(
        Change,
        factory,
        result_type=Reply,
        operation="invalid",
        idempotency_policy=IdempotencyPolicy(mode=storage_mode)
        if storage_mode
        else None,
    )
    bus = build_bus(monkeypatch, registry, state)
    with pytest.raises(ValidationError):
        await bus.dispatch(
            Change(value="x"), context(), result_mode=ResultMode.COMPLETION_ONLY
        )
    assert not state.effects and not state.records and not state.hot


@pytest.mark.parametrize("winner_mode", list(ResultMode))
async def test_concurrent_mixed_modes_use_winner_and_rollback_loser(
    monkeypatch, winner_mode
):
    state, registry = State(hot_unavailable=True), CommandHandlerRegistry()
    first_started, winner_finished = asyncio.Event(), asyncio.Event()
    both_started = asyncio.Barrier(2)
    calls = []

    def factory(session):
        async def handler(command):
            number = len(calls)
            calls.append(session)
            session.stage(number)
            first_started.set()
            await both_started.wait()
            if number == 1:
                await winner_finished.wait()
            return Reply(value=str(number))

        return handler

    registry.register(
        Change,
        factory,
        result_type=Reply,
        operation="race",
        idempotency_policy=IdempotencyPolicy(),
    )
    bus = build_bus(monkeypatch, registry, state)

    async def winning_attempt():
        try:
            return await bus.dispatch(
                Change(value="same"), context(), result_mode=winner_mode
            )
        finally:
            winner_finished.set()

    loser_mode = (
        ResultMode.COMPLETION_ONLY
        if winner_mode is ResultMode.REPLAYABLE
        else ResultMode.REPLAYABLE
    )
    async with asyncio.timeout(5):
        winner = asyncio.create_task(winning_attempt())
        await first_started.wait()
        loser = asyncio.create_task(
            bus.dispatch(Change(value="same"), context(), result_mode=loser_mode)
        )
        result, other = await asyncio.gather(winner, loser, return_exceptions=True)

    if winner_mode is ResultMode.REPLAYABLE:
        assert result == Reply(value="0") and other is None
    else:
        assert result is None
        assert isinstance(other, IdempotencyResultNotStoredError)
    assert state.effects == [0]
    assert len(state.records) == 1
    assert len(calls) == 2 and calls[0] is not calls[1]
    assert all(session.closed and not session.active for session in calls)


def test_stored_none_is_distinct_from_a_completion_marker():
    codec = PydanticResultCodec(NoneType)
    snapshot = codec.encode(None)
    marker = StoredResult.completion()
    assert snapshot.result_payload == {"value": None}
    assert not snapshot.is_completion_only
    assert codec.decode(snapshot) is None
    assert marker.result_payload is None
    with pytest.raises(IdempotencyResultNotStoredError):
        codec.decode(marker)


@pytest.mark.parametrize(
    "fields",
    [
        {"result_payload": {}},
        {"result_payload": {"value": None}},
        {"resource_type": "profile", "resource_id": "id"},
        {"resource_version": 1},
    ],
)
def test_completion_marker_cannot_carry_snapshot_or_resource(fields):
    with pytest.raises(ValidationError):
        StoredResult(result_type="completion", **fields)


async def test_unknown_result_mode_fails_before_scope_and_handler(monkeypatch):
    state, calls = State(), []
    bus = build_bus(
        monkeypatch, registry_with_handler(IdempotencyPolicy(), calls), state
    )
    with pytest.raises(TypeError, match="result_mode"):
        await bus.dispatch(Change(value="x"), context(), result_mode="completion")
    assert not calls and not state.sessions


async def test_completion_replay_does_not_require_old_dto_schema(monkeypatch):
    state, calls = State(), []
    await build_bus(
        monkeypatch, registry_with_handler(IdempotencyPolicy(), calls), state
    ).dispatch(Change(value="x"), context())
    registry = CommandHandlerRegistry()

    def forbidden(_):
        pytest.fail("completion replay must not construct the handler")

    registry.register(
        Change,
        forbidden,
        result_type=Reply,
        result_schema_version=2,
        operation="profile.change",
        idempotency_policy=IdempotencyPolicy(),
    )
    bus = build_bus(monkeypatch, registry, state)
    assert (
        await bus.dispatch(
            Change(value="x"), context(), result_mode=ResultMode.COMPLETION_ONLY
        )
        is None
    )
    assert len(calls) == 1

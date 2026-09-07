import asyncio
from types import NoneType
from typing import Any

import pytest
from fakes import State, build_bus
from pydantic import BaseModel, ValidationError

from app.application.commands.base import BaseCommand
from app.application.dispatching.context import CommandContext
from app.application.dispatching.registry import CommandHandlerRegistry
from app.application.exceptions.idempotency import (
    IdempotencyConflictError,
    IdempotencyKeyRequiredError,
    IdempotencyScopeRequiredError,
)
from app.application.idempotency.policy import IdempotencyMode, IdempotencyPolicy


class Response(BaseModel):
    value: str


class Change(BaseCommand[Response]):
    value: str


def context(key="key", scope="user:trusted"):
    return CommandContext(idempotency_key=key, idempotency_scope=scope)


def register(registry, policy, calls):
    def factory(session):
        async def handler(command):
            calls.append(session)
            session.stage(command.value)
            return Response(value=command.value)

        return handler

    registry.register(
        Change,
        factory,
        result_type=Response,
        operation="profile.change.v1",
        idempotency_policy=policy,
    )


@pytest.mark.parametrize("mode", [None, *IdempotencyMode])
async def test_dispatch_uses_fresh_scopes_and_only_idempotent_commands_replay(
    monkeypatch, mode
):
    state, calls, registry = State(), [], CommandHandlerRegistry()
    policy = IdempotencyPolicy(mode=mode) if mode else None
    register(registry, policy, calls)
    bus = build_bus(monkeypatch, registry, state)
    first = await bus.dispatch(Change(value="x"), context())
    second = await bus.dispatch(Change(value="x"), context())
    assert first == second == Response(value="x")
    assert len(calls) == (2 if mode is None else 1)
    assert len(state.effects) == len(calls)
    assert len(state.sessions) == 2
    assert state.sessions[0] is not state.sessions[1]
    assert all(s.closed and not s.active for s in state.sessions)
    assert len(state.records) == (1 if mode is IdempotencyMode.HOT_DURABLE else 0)


async def test_concurrent_dispatches_rollback_loser_and_return_same_winner(monkeypatch):
    state, registry = State(hot_unavailable=True), CommandHandlerRegistry()
    barrier = asyncio.Barrier(2)
    calls = []

    def factory(session):
        async def handler(command):
            number = len(calls)
            calls.append(session)
            session.stage(number)
            await barrier.wait()
            return Response(value=str(number))

        return handler

    registry.register(
        Change,
        factory,
        result_type=Response,
        operation="change",
        idempotency_policy=IdempotencyPolicy(),
    )
    bus = build_bus(monkeypatch, registry, state)
    async with asyncio.timeout(5):
        left, right = await asyncio.gather(
            bus.dispatch(Change(value="x"), context()),
            bus.dispatch(Change(value="x"), context()),
        )
    assert left == right
    assert len(calls) == 2 and calls[0] is not calls[1]
    assert state.effects == [int(left.value)]
    assert len(state.records) == 1


@pytest.mark.parametrize("mode", [None, *IdempotencyMode])
async def test_invalid_handler_result_rolls_back_before_commit(monkeypatch, mode):
    state, registry = State(), CommandHandlerRegistry()

    def factory(session):
        async def handler(command):
            session.stage("must rollback")
            return 123

        return handler

    registry.register(
        Change,
        factory,
        result_type=Response,
        operation="bad-result",
        idempotency_policy=IdempotencyPolicy(mode=mode) if mode else None,
    )
    bus = build_bus(monkeypatch, registry, state)
    with pytest.raises(ValidationError):
        await bus.dispatch(Change(value="x"), context())
    assert not state.effects and not state.records


@pytest.mark.parametrize(
    ("ctx", "error"),
    [
        (CommandContext(idempotency_scope="user:1"), IdempotencyKeyRequiredError),
        (
            CommandContext(idempotency_key="k", actor_id="user:1"),
            IdempotencyScopeRequiredError,
        ),
    ],
)
async def test_missing_trusted_context_cannot_fall_back_to_command_fields(
    monkeypatch, ctx, error
):
    state, calls, registry = State(), [], CommandHandlerRegistry()
    register(registry, IdempotencyPolicy(), calls)
    bus = build_bus(monkeypatch, registry, state)
    with pytest.raises(error):
        await bus.dispatch(Change(value="x"), ctx)
    assert not calls and not state.effects


async def test_scopes_are_isolated_and_context_is_not_fingerprinted(monkeypatch):
    state, calls, registry = State(), [], CommandHandlerRegistry()
    register(registry, IdempotencyPolicy(), calls)
    bus = build_bus(monkeypatch, registry, state)
    await bus.dispatch(Change(value="x"), context(scope="user:a"))
    await bus.dispatch(Change(value="x"), context(scope="user:b"))
    await bus.dispatch(
        Change(value="x"),
        context(scope="user:a").model_copy(update={"correlation_id": "new"}),
    )
    assert len(calls) == 2
    with pytest.raises(IdempotencyConflictError):
        await bus.dispatch(Change(value="different"), context(scope="user:a"))


@pytest.mark.parametrize("evict_hot", [False, True])
async def test_warming_hot_never_extends_durable_retention(monkeypatch, evict_hot):
    state, calls, registry = State(), [], CommandHandlerRegistry()
    policy = IdempotencyPolicy(retention_seconds=10, hot_cache_seconds=6)
    register(registry, policy, calls)
    bus = build_bus(monkeypatch, registry, state)
    command = Change(value="x")
    await bus.dispatch(command, context())
    deadline = next(iter(state.records.values())).expires_at
    state.clock.advance(9)  # HOT expired; DURABLE has one second left.
    await bus.dispatch(command, context())
    assert len(calls) == 1
    assert next(iter(state.hot.values()))["expires"] == deadline
    if evict_hot:
        state.hot.clear()
    state.clock.advance(2)
    await bus.dispatch(command, context())
    assert len(calls) == 2
    assert next(iter(state.records.values())).expires_at > deadline


async def test_stable_operation_survives_command_class_rename(monkeypatch):
    class RenamedChange(Change):
        pass

    state, calls, first_registry = State(), [], CommandHandlerRegistry()
    register(first_registry, IdempotencyPolicy(), calls)
    await build_bus(monkeypatch, first_registry, state).dispatch(
        Change(value="x"), context()
    )
    second_registry = CommandHandlerRegistry()

    def forbidden(_):
        pytest.fail("replay must not construct a handler")

    second_registry.register(
        RenamedChange,
        forbidden,
        result_type=Response,
        operation="profile.change.v1",
        idempotency_policy=IdempotencyPolicy(),
    )
    result = await build_bus(monkeypatch, second_registry, state).dispatch(
        RenamedChange(value="x"), context()
    )
    assert result == Response(value="x")


def test_registry_is_frozen_when_bus_is_built(monkeypatch):
    registry = CommandHandlerRegistry()
    build_bus(monkeypatch, registry, State())
    with pytest.raises(RuntimeError, match="frozen"):
        register(registry, IdempotencyPolicy(), [])


@pytest.mark.parametrize(
    ("operation", "schema", "error"),
    [
        ("", Response, ValueError),
        ("  ", Response, ValueError),
        ("valid", Any, TypeError),
        ("valid", object(), Exception),
    ],
)
def test_invalid_registration_rejected_at_assembly(operation, schema, error):
    with pytest.raises(error):
        CommandHandlerRegistry().register(
            Change, lambda _: None, result_type=schema, operation=operation
        )


@pytest.mark.parametrize(
    ("schema", "value"),
    [(NoneType, None), (int, 42), (list[int], [1, 2]), (dict[str, int], {"value": 42})],
)
async def test_registered_schemas_restore_same_result_on_replay(
    monkeypatch, schema, value
):
    class Example(BaseCommand[Any]):
        pass

    state, calls, registry = State(), [], CommandHandlerRegistry()

    def factory(session):
        async def handler(command):
            calls.append(session)
            return value

        return handler

    registry.register(
        Example,
        factory,
        result_type=schema,
        operation="example",
        idempotency_policy=IdempotencyPolicy(),
    )
    bus = build_bus(monkeypatch, registry, state)
    assert await bus.dispatch(Example(), context()) == value
    assert await bus.dispatch(Example(), context()) == value
    assert len(calls) == 1


async def test_cancellation_rolls_back_and_closes_dispatch_scope(monkeypatch):
    entered = asyncio.Event()
    state, registry = State(), CommandHandlerRegistry()

    def factory(session):
        async def handler(command):
            session.stage("cancelled")
            entered.set()
            await asyncio.Event().wait()

        return handler

    registry.register(
        Change,
        factory,
        result_type=Response,
        operation="cancel",
        idempotency_policy=IdempotencyPolicy(),
    )
    bus = build_bus(monkeypatch, registry, state)
    task = asyncio.create_task(bus.dispatch(Change(value="x"), context()))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not state.effects and not state.records
    assert state.sessions[0].closed and not state.sessions[0].active

import uuid

import pytest
from pydantic import BaseModel, Field

from app.application.commands.base import BaseCommand
from app.application.dispatching import (
    CommandBus,
    CommandContext,
    CommandHandlerRegistry,
)
from app.application.exceptions.idempotency import (
    IdempotencyConflictError,
    IdempotencyKeyRequiredError,
)
from app.application.idempotency.coordinator import IdempotencyCoordinator
from app.application.idempotency.middleware import IdempotencyMiddleware
from app.application.idempotency.models import (
    ClaimResult,
    ClaimStatus,
    CompletedIdempotencyResult,
    IdempotencyKey,
)
from app.application.idempotency.policy import IdempotencyMode, IdempotencyPolicy


class ProfileResponse(BaseModel):
    user_id: uuid.UUID
    bio: str
    version: int = 1


class UpdateBioCommand(BaseCommand[ProfileResponse]):
    user_id: uuid.UUID
    bio: str = Field(max_length=255)


class FakeMemoryHotStore:
    def __init__(self) -> None:
        self.store: dict[str, CompletedIdempotencyResult] = {}
        self.processing: set[str] = set()

    def _key(self, identity: IdempotencyKey) -> str:
        return f"{identity.subject_id}:{identity.operation}:{identity.key_digest.hex()}"

    async def claim(
        self,
        identity: IdempotencyKey,
        request_fingerprint: bytes,
        lease_token: uuid.UUID,
        lease_seconds: int,
    ) -> ClaimResult:
        k = self._key(identity)
        if k in self.store:
            completed = self.store[k]
            if completed.request_fingerprint != request_fingerprint:
                return ClaimResult(status=ClaimStatus.CONFLICT)
            return ClaimResult(status=ClaimStatus.REPLAY, completed=completed)
        if k in self.processing:
            return ClaimResult(status=ClaimStatus.IN_PROGRESS)
        self.processing.add(k)
        return ClaimResult(status=ClaimStatus.ACQUIRED)

    async def renew(
        self, identity: IdempotencyKey, lease_token: uuid.UUID, lease_seconds: int
    ) -> bool:
        return True

    async def complete(
        self,
        identity: IdempotencyKey,
        lease_token: uuid.UUID,
        result: CompletedIdempotencyResult,
    ) -> bool:
        k = self._key(identity)
        self.processing.discard(k)
        self.store[k] = result
        return True

    async def release(self, identity: IdempotencyKey, lease_token: uuid.UUID) -> bool:
        k = self._key(identity)
        self.processing.discard(k)
        return True


async def test_command_bus_direct_dispatch_without_policy():
    registry = CommandHandlerRegistry()

    called = False

    async def handler(cmd: UpdateBioCommand) -> ProfileResponse:
        nonlocal called
        called = True
        return ProfileResponse(user_id=cmd.user_id, bio=cmd.bio)

    registry.register(UpdateBioCommand, handler)
    bus = CommandBus(registry=registry)
    assert not hasattr(bus, "register")

    u_id = uuid.uuid4()
    cmd = UpdateBioCommand(user_id=u_id, bio="Hello world")
    res = await bus.dispatch(cmd)

    assert called is True
    assert res.user_id == u_id
    assert res.bio == "Hello world"


async def test_command_bus_with_idempotency_middleware():
    hot_store = FakeMemoryHotStore()
    coordinator = IdempotencyCoordinator(hot_store=hot_store)
    middleware = IdempotencyMiddleware(coordinator=coordinator)

    call_count = 0

    async def handler(cmd: UpdateBioCommand) -> ProfileResponse:
        nonlocal call_count
        call_count += 1
        return ProfileResponse(user_id=cmd.user_id, bio=cmd.bio, version=call_count)

    registry = CommandHandlerRegistry()
    policy = IdempotencyPolicy(mode=IdempotencyMode.HOT_ONLY, lease_seconds=30)
    registry.register(UpdateBioCommand, handler, idempotency_policy=policy)

    bus = CommandBus(registry=registry, idempotency_middleware=middleware)

    user_id = uuid.uuid4()
    cmd = UpdateBioCommand(user_id=user_id, bio="Bio 1")
    context = CommandContext(idempotency_key="key-123", actor_id=str(user_id))

    # First dispatch -> Executed
    res1 = await bus.dispatch(cmd, context=context)
    assert call_count == 1
    assert res1.user_id == user_id
    assert res1.bio == "Bio 1"
    assert res1.version == 1

    # Second dispatch with identical key and command -> Replay without calling handler
    res2 = await bus.dispatch(cmd, context=context)
    assert call_count == 1  # handler not called again
    assert res2["user_id"] == user_id
    assert res2["bio"] == "Bio 1"
    assert res2["version"] == 1

    # Third dispatch with same key but different command payload -> Conflict exception
    cmd_conflict = UpdateBioCommand(user_id=user_id, bio="Different bio")
    with pytest.raises(IdempotencyConflictError):
        await bus.dispatch(cmd_conflict, context=context)


def test_command_context_validation():
    from pydantic import ValidationError

    # Valid contexts
    context = CommandContext(
        idempotency_key="key-1",
        actor_id="user-1",
        correlation_id="corr-1",
    )
    assert context.idempotency_key == "key-1"
    assert context.actor_id == "user-1"
    assert context.correlation_id == "corr-1"

    # Default None values
    empty_context = CommandContext()
    assert empty_context.idempotency_key is None
    assert empty_context.actor_id is None
    assert empty_context.correlation_id is None

    # Empty string rejected by min_length=1
    with pytest.raises(ValidationError):
        CommandContext(idempotency_key="")

    with pytest.raises(ValidationError):
        CommandContext(actor_id="")

    with pytest.raises(ValidationError):
        CommandContext(correlation_id="")

    # Extra fields rejected by extra="forbid"
    with pytest.raises(ValidationError):
        CommandContext(extra_field="disallowed")  # type: ignore[call-arg]


async def test_command_bus_requires_idempotency_key_when_policy_exists():
    hot = FakeMemoryHotStore()
    coordinator = IdempotencyCoordinator(hot_store=hot)
    middleware = IdempotencyMiddleware(coordinator=coordinator)

    registry = CommandHandlerRegistry()
    policy = IdempotencyPolicy(mode=IdempotencyMode.HOT_ONLY)

    async def handler(cmd: UpdateBioCommand) -> ProfileResponse:
        return ProfileResponse(user_id=cmd.user_id, bio=cmd.bio)

    registry.register(UpdateBioCommand, handler, idempotency_policy=policy)
    bus = CommandBus(registry=registry, idempotency_middleware=middleware)

    cmd = UpdateBioCommand(user_id=uuid.uuid4(), bio="test")
    context_without_key = CommandContext(actor_id="user-1")

    with pytest.raises(
        IdempotencyKeyRequiredError,
        match="Ключ идемпотентности обязателен для команды 'UpdateBioCommand'",
    ):
        await bus.dispatch(cmd, context=context_without_key)


def test_command_bus_fail_fast_when_policy_without_middleware():
    registry = CommandHandlerRegistry()
    policy = IdempotencyPolicy(mode=IdempotencyMode.HOT_ONLY)

    async def handler(cmd: UpdateBioCommand) -> ProfileResponse:
        return ProfileResponse(user_id=cmd.user_id, bio=cmd.bio)

    registry.register(UpdateBioCommand, handler, idempotency_policy=policy)

    with pytest.raises(
        RuntimeError,
        match="Ошибка конфигурации: для команды 'UpdateBioCommand' задана политика",
    ):
        CommandBus(registry=registry, idempotency_middleware=None)


def test_command_bus_fail_fast_when_hot_durable_without_durable_storage():
    hot = FakeMemoryHotStore()
    coordinator = IdempotencyCoordinator(hot_store=hot, durable_execution=None)
    middleware = IdempotencyMiddleware(coordinator=coordinator)

    registry = CommandHandlerRegistry()
    policy = IdempotencyPolicy(mode=IdempotencyMode.HOT_DURABLE)

    async def handler(cmd: UpdateBioCommand) -> ProfileResponse:
        return ProfileResponse(user_id=cmd.user_id, bio=cmd.bio)

    registry.register(UpdateBioCommand, handler, idempotency_policy=policy)

    with pytest.raises(
        RuntimeError,
        match="Ошибка конфигурации: команда 'UpdateBioCommand' требует режим HOT_DURABLE",
    ):
        CommandBus(registry=registry, idempotency_middleware=middleware)

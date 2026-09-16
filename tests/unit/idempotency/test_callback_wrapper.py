import pytest
from fakes import HotStore, State

from app.application.exceptions.idempotency import (
    IdempotencyKeyRequiredError,
    IdempotencyScopeRequiredError,
)
from app.application.idempotency.coordinator import IdempotencyCoordinator
from app.application.idempotency.middleware import IdempotencyMiddleware
from app.application.idempotency.models import StoredResult
from app.application.idempotency.policy import IdempotencyMode, IdempotencyPolicy


@pytest.mark.parametrize("completion_only", [False, True])
async def test_plain_callback_can_be_replayed_without_a_command(completion_only):
    state = State()
    wrapper = IdempotencyMiddleware(
        IdempotencyCoordinator(HotStore(state), clock=state.clock)
    )
    calls = []

    async def operation():
        calls.append("executed")
        return (
            StoredResult.completion()
            if completion_only
            else StoredResult(result_type="snapshot", result_payload={"value": 42})
        )

    kwargs = dict(
        key="request-1",
        scope="user:1",
        operation_name="example",
        request_fingerprint=b"f" * 32,
        policy=IdempotencyPolicy(mode=IdempotencyMode.HOT_ONLY),
    )
    original = await wrapper.execute(operation, **kwargs)
    replay = await wrapper.execute(operation, **kwargs)
    assert replay == original
    assert replay.is_completion_only == completion_only
    assert calls == ["executed"]


@pytest.mark.parametrize(
    "key, scope, error",
    [
        (None, "user:1", IdempotencyKeyRequiredError),
        ("request-1", None, IdempotencyScopeRequiredError),
    ],
)
async def test_missing_identity_does_not_start_callback(key, scope, error):
    state = State()
    wrapper = IdempotencyMiddleware(
        IdempotencyCoordinator(HotStore(state), clock=state.clock)
    )

    async def operation():
        pytest.fail("Invalid identity must be rejected before execution")

    with pytest.raises(error):
        await wrapper.execute(
            operation,
            key=key,
            scope=scope,
            operation_name="example",
            request_fingerprint=b"f" * 32,
            policy=IdempotencyPolicy(mode=IdempotencyMode.HOT_ONLY),
        )
    assert not state.hot

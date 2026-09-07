import pytest

from .support import HandlerHarness


@pytest.fixture
def harness() -> HandlerHarness:
    """Fresh storage, deterministic clock and identities for each test."""
    return HandlerHarness()

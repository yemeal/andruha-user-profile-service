import os
from collections.abc import Iterator

import pytest

from app.core.settings import get_settings

# Provide test defaults so tests run in environments without a pre-configured .env
os.environ.setdefault("POSTGRES_HOST", "127.0.0.1")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_USER", "andruha_profile")
os.environ.setdefault("POSTGRES_PASSWORD", "profile-local-only")
os.environ.setdefault("POSTGRES_DB", "andruha_profile")
os.environ.setdefault("REDIS_HOST", "127.0.0.1")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_DB", "0")


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()

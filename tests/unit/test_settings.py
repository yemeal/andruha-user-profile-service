import pytest

from app.core.settings import (
    InternalAPISettings,
    PostgresSettings,
    RedisSettings,
    _read_bool,
    _read_mute_loggers,
    _read_port,
    get_settings,
)


def test_internal_service_token_uses_core_environment_and_is_redacted(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", "private-service-credential")
    settings = InternalAPISettings()
    assert settings.token is not None
    assert settings.token.get_secret_value() == "private-service-credential"
    assert "private-service-credential" not in repr(settings)


@pytest.mark.parametrize("raw_value", ["1", "true", "TRUE", " yes ", "on"])
def test_read_bool_accepts_true_values(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
) -> None:
    monkeypatch.setenv("FEATURE", raw_value)

    assert _read_bool("FEATURE", False) is True


@pytest.mark.parametrize("raw_value", ["0", "false", "FALSE", " no ", "off"])
def test_read_bool_accepts_false_values(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
) -> None:
    monkeypatch.setenv("FEATURE", raw_value)

    assert _read_bool("FEATURE", True) is False


def test_read_bool_uses_default_when_variable_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FEATURE", raising=False)

    assert _read_bool("FEATURE", True) is True


def test_read_bool_rejects_unknown_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEATURE", "sometimes")

    with pytest.raises(ValueError, match="FEATURE must be a boolean value"):
        _read_bool("FEATURE", False)


@pytest.mark.parametrize("port", [1, 8001, 65535])
def test_read_port_accepts_valid_range(
    monkeypatch: pytest.MonkeyPatch,
    port: int,
) -> None:
    monkeypatch.setenv("PORT", str(port))

    assert _read_port(9000) == port


@pytest.mark.parametrize("port", [0, 65536])
def test_read_port_rejects_out_of_range_value(
    monkeypatch: pytest.MonkeyPatch,
    port: int,
) -> None:
    monkeypatch.setenv("PORT", str(port))

    with pytest.raises(ValueError, match="PORT must be between 1 and 65535"):
        _read_port(9000)


def test_read_port_rejects_non_numeric_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PORT", "http")

    with pytest.raises(ValueError):
        _read_port(9000)


def test_read_mute_loggers_trims_and_drops_empty_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MUTE_LOGGERS", " uvicorn.access, ,httpx ")

    assert _read_mute_loggers() == ("uvicorn.access", "httpx")


def test_get_settings_reads_explicit_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "SERVICE_NAME": "test-service",
        "APP_VERSION": "9.9.9",
        "APP_ENVIRONMENT": "test",
        "HOST": "127.0.0.1",
        "PORT": "9123",
        "DEV_LOGS": "false",
        "LOG_LEVEL": "debug",
        "MUTE_LOGGERS": "httpx,uvicorn.access",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    settings = get_settings()

    assert settings.app.service_name == "test-service"
    assert settings.app.version == "9.9.9"
    assert settings.app.environment == "test"
    assert settings.app.host == "127.0.0.1"
    assert settings.app.port == 9123
    assert settings.app.dev_logs is False
    assert settings.app.log_level == "DEBUG"
    assert settings.app.mute_loggers == ("httpx", "uvicorn.access")


def test_postgres_settings_assembled_from_components() -> None:
    settings = PostgresSettings(
        host="db.internal",
        port=5433,
        user="myuser",
        password="mypassword",
        db="mydb",
    )
    assert (
        settings.database_url.get_secret_value()
        == "postgresql+asyncpg://myuser:mypassword@db.internal:5433/mydb"
    )
    assert settings.url == settings.database_url


def test_postgres_settings_accepts_direct_url() -> None:
    settings = PostgresSettings(
        database_url="postgresql+asyncpg://custom_user:custom_pass@custom_host:5432/custom_db"
    )
    assert (
        settings.database_url.get_secret_value()
        == "postgresql+asyncpg://custom_user:custom_pass@custom_host:5432/custom_db"
    )


def test_postgres_settings_requires_mandatory_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for var in [
        "DATABASE_URL",
        "PROFILE_DATABASE_URL",
        "POSTGRES_HOST",
        "PROFILE_POSTGRES_HOST",
        "DATABASE_HOST",
        "PROFILE_DATABASE_HOST",
    ]:
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(ValueError, match="PostgreSQL connection settings are required"):
        PostgresSettings()


def test_redis_settings_assembled_from_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_IDEMPOTENCY_REDIS_URL", raising=False)
    settings = RedisSettings(host="cache.internal", port=6380, db=2)
    assert settings.url.get_secret_value() == "redis://cache.internal:6380/2"


def test_redis_settings_accepts_direct_url() -> None:
    settings = RedisSettings(url="redis://custom:6379/1")
    assert settings.url.get_secret_value() == "redis://custom:6379/1"


def test_redis_settings_requires_mandatory_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for var in [
        "REDIS_URL",
        "PROFILE_REDIS_URL",
        "REDIS_HOST",
        "PROFILE_REDIS_HOST",
        "VALKEY_URL",
        "PROFILE_VALKEY_URL",
        "TEST_IDEMPOTENCY_REDIS_URL",
    ]:
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(ValueError, match="Redis connection settings are required"):
        RedisSettings()

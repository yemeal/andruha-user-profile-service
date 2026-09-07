import logging

import pytest

from app.core.logging import _log_level, _service_context, setup_logging
from app.core.settings import AppSettings


def make_settings(*, dev_logs: bool, log_level: str = "INFO") -> AppSettings:
    return AppSettings(
        service_name="test-service",
        version="1.2.3",
        environment="test",
        host="127.0.0.1",
        port=9000,
        dev_logs=dev_logs,
        log_level=log_level,
        mute_loggers=("chatty",),
    )


def test_log_level_resolves_known_level() -> None:
    assert _log_level(make_settings(dev_logs=True, log_level="WARNING")) == 30


def test_log_level_rejects_unknown_level() -> None:
    with pytest.raises(ValueError, match="Unsupported LOG_LEVEL"):
        _log_level(make_settings(dev_logs=True, log_level="LOUD"))


def test_service_context_adds_defaults_without_overwriting_values() -> None:
    processor = _service_context(make_settings(dev_logs=True))
    event = {"service": "already-bound"}

    result = processor(None, "info", event)

    assert result == {
        "service": "already-bound",
        "version": "1.2.3",
        "environment": "test",
    }


@pytest.mark.parametrize("dev_logs", [True, False])
def test_setup_logging_configures_root_and_muted_loggers(dev_logs: bool) -> None:
    logging.getLogger("chatty")

    setup_logging(make_settings(dev_logs=dev_logs, log_level="DEBUG"))

    assert logging.getLogger().level == logging.DEBUG
    assert logging.getLogger("chatty").level == logging.WARNING
    assert logging.getLogger("chatty").propagate is True

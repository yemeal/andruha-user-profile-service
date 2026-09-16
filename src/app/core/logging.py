"""Structured logging bootstrap for the service process."""

import logging
import logging.config
from collections.abc import MutableMapping
from typing import Any

import structlog

from app.core.settings import AppSettings, Settings, get_settings

EventDict = MutableMapping[str, Any]


def _log_level(settings: AppSettings) -> int:
    level = logging.getLevelNamesMapping().get(settings.log_level)
    if level is None:
        raise ValueError(f"Unsupported LOG_LEVEL: {settings.log_level}")
    return level


def _service_context(settings: AppSettings):
    def add_service_context(
        _logger: object,
        _method_name: str,
        event_dict: EventDict,
    ) -> EventDict:
        event_dict.setdefault("service", settings.service_name)
        event_dict.setdefault("version", settings.version)
        event_dict.setdefault("environment", settings.environment)
        return event_dict

    return add_service_context


def setup_logging(settings: AppSettings | Settings | None = None) -> None:
    if settings is None:
        current_settings = get_settings().app
    elif isinstance(settings, Settings):
        current_settings = settings.app
    else:
        current_settings = settings

    level = _log_level(current_settings)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        _service_context(current_settings),
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer = (
        structlog.dev.ConsoleRenderer()
        if current_settings.dev_logs
        else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "structured": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "foreign_pre_chain": shared_processors,
                    "processors": [
                        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                        renderer,
                    ],
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "structured",
                }
            },
            "root": {
                "handlers": ["default"],
                "level": level,
            },
        }
    )

    for logger_name in logging.root.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(
            max(level, logging.WARNING)
            if logger_name in current_settings.mute_loggers
            else level
        )

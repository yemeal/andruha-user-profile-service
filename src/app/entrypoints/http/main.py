"""FastAPI application factory for User Profile Service."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from dishka import AsyncContainer
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from app.core.logging import setup_logging
from app.core.settings import AppSettings
from app.entrypoints.http.di import HTTPProvider
from app.entrypoints.http.exception_handlers import register_exception_handlers
from app.entrypoints.http.middlewares import RequestIdMiddleware
from app.entrypoints.http.routers import (
    health_router,
    internal_router,
    profiles_router,
    settings_router,
)
from app.entrypoints.http.security import AccessTokenVerifier
from app.infrastructure.di import create_container

logger = structlog.get_logger()


def create_app(container: AsyncContainer | None = None) -> FastAPI:
    app_container = container or create_container(HTTPProvider())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        try:
            settings = await app_container.get(AppSettings)
            setup_logging(settings)
            app.version = settings.version
            await app_container.get(AccessTokenVerifier | None)
            app.state.ready = True
            logger.info("application started", version=app.version)
            yield
        finally:
            app.state.ready = False
            logger.info("application shutting down")
            await app_container.close()

    app = FastAPI(
        title="Andruha Messenger / User Profile Service",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.ready = False
    register_exception_handlers(app)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health_router)
    app.include_router(profiles_router)
    app.include_router(settings_router)
    app.include_router(internal_router)
    setup_dishka(app_container, app)
    return app

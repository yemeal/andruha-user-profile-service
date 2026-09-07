"""FastAPI application factory for User Profile Service."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from dishka import AsyncContainer
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from app.core.logging import setup_logging
from app.core.settings import get_settings
from app.entrypoints.http.middlewares import RequestIdMiddleware
from app.entrypoints.http.routers.health import router as health_router
from app.infrastructure.di import create_container

logger = structlog.get_logger()


def create_app(container: AsyncContainer | None = None) -> FastAPI:
    settings = get_settings()
    setup_logging(settings.app)
    app_container = container or create_container()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        app.state.ready = True
        logger.info("application started", version=app.version)
        try:
            yield
        finally:
            app.state.ready = False
            logger.info("application shutting down")
            await app_container.close()

    app = FastAPI(
        title="Andruha Messenger / User Profile Service",
        version=settings.app.version,
        lifespan=lifespan,
    )
    app.state.ready = False
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health_router)
    setup_dishka(app_container, app)
    return app

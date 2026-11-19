"""Process liveness and dependency-aware application readiness."""

import asyncio

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.entrypoints.http.security import AccessTokenVerifier
from app.infrastructure.database.models import ProfileORM, SettingsORM
from app.infrastructure.idempotency.postgres.models import IdempotencyRecordORM

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
@inject
async def ready(
    request: Request,
    response: Response,
    sessions: FromDishka[async_sessionmaker[AsyncSession]],
    verifier: FromDishka[AccessTokenVerifier | None],
) -> dict[str, str]:
    is_ready = bool(getattr(request.app.state, "ready", False)) and verifier is not None
    if is_ready:
        try:
            async with asyncio.timeout(2), sessions() as session:
                for model in (ProfileORM, SettingsORM, IdempotencyRecordORM):
                    await session.execute(select(model).limit(0))
        except Exception:
            is_ready = False
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {"status": "ready" if is_ready else "unavailable"}

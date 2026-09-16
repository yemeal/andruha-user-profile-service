"""Internal profile provisioning and existence; never published by the gateway."""

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Depends, Response

from app.application.commands.profiles.create_default.command import (
    CreateDefaultProfileCommand,
)
from app.application.dispatching.bus import CommandBusProtocol
from app.application.dispatching.context import CommandContext
from app.application.dispatching.result_mode import ResultMode
from app.application.queries.profiles.check_exists.handler import (
    CheckProfileExistsHandler,
)
from app.application.queries.profiles.check_exists.query import CheckProfileExistsQuery
from app.entrypoints.http.dependencies import require_identity_service
from app.entrypoints.http.schemas import ProvisionProfileRequest

router = APIRouter(
    prefix="/internal/v1/profiles", tags=["internal"], route_class=DishkaRoute
)


@router.put(
    "/{user_id}", status_code=204, dependencies=[Depends(require_identity_service)]
)
async def provision_profile(
    user_id: UUID,
    body: ProvisionProfileRequest,
    commands: FromDishka[CommandBusProtocol],
) -> Response:
    await commands.dispatch(
        CreateDefaultProfileCommand(user_id=user_id, registered_at=body.registered_at),
        CommandContext(
            idempotency_key=str(user_id),
            idempotency_scope="identity:profile-provisioning",
            actor_id="identity-service",
        ),
        result_mode=ResultMode.COMPLETION_ONLY,
    )
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.head("/{user_id}")
async def profile_exists(
    user_id: UUID, handler: FromDishka[CheckProfileExistsHandler]
) -> Response:
    exists = await handler(CheckProfileExistsQuery(user_id=user_id))
    return Response(
        status_code=200 if exists else 404, headers={"Cache-Control": "no-store"}
    )

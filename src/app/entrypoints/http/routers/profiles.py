"""Profile read endpoints backed by the existing application queries."""

from typing import Annotated
from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Query, Response

from app.application.commands.profiles.update.command import UpdateProfileCommand
from app.application.dispatching.bus import CommandBusProtocol
from app.application.dto.profiles import ProfileDTO, PublicProfileDTO
from app.application.queries.profiles.get_batch.handler import GetBatchProfilesHandler
from app.application.queries.profiles.get_batch.query import GetBatchProfilesQuery
from app.application.queries.profiles.get_my.handler import GetMyProfileHandler
from app.application.queries.profiles.get_my.query import GetMyProfileQuery
from app.application.queries.profiles.get_public.handler import GetPublicProfileHandler
from app.application.queries.profiles.get_public.query import GetPublicProfileQuery
from app.application.queries.profiles.search_by_username.handler import (
    SearchByUsernameHandler,
)
from app.application.queries.profiles.search_by_username.query import (
    SearchByUsernameQuery,
)
from app.entrypoints.http.dependencies import (
    CurrentUserId,
    ExpectedVersion,
    HTTPCommandContext,
    OptionalViewerId,
)
from app.entrypoints.http.responses import set_private_version
from app.entrypoints.http.schemas import BatchProfilesRequest, ProfilePatchRequest

router = APIRouter(
    prefix="/api/v1/profiles", tags=["profiles"], route_class=DishkaRoute
)


@router.get("/me")
async def get_my_profile(
    user_id: CurrentUserId,
    handler: FromDishka[GetMyProfileHandler],
    response: Response,
) -> ProfileDTO:
    profile = await handler(GetMyProfileQuery(user_id=user_id))
    set_private_version(response, profile.version)
    return profile


@router.patch("/me")
async def patch_my_profile(
    user_id: CurrentUserId,
    version: ExpectedVersion,
    context: HTTPCommandContext,
    body: ProfilePatchRequest,
    commands: FromDishka[CommandBusProtocol],
    response: Response,
) -> ProfileDTO:
    profile = await commands.dispatch(
        UpdateProfileCommand(
            user_id=user_id,
            expected_version=version,
            display_name=body.display_name,
            username=body.username,
            bio=(body.bio or "") if "bio" in body.model_fields_set else None,
        ),
        context,
    )
    set_private_version(response, profile.version)
    return profile


@router.get("")
async def search_profiles(
    username: Annotated[str, Query(min_length=3, max_length=32)],
    viewer_id: OptionalViewerId,
    handler: FromDishka[SearchByUsernameHandler],
    response: Response,
) -> PublicProfileDTO:
    profile = await handler(
        SearchByUsernameQuery(username=username, viewer_id=viewer_id)
    )
    response.headers["Cache-Control"] = "no-store"
    return profile


@router.post("/batch")
async def get_batch_profiles(
    body: BatchProfilesRequest,
    viewer_id: OptionalViewerId,
    handler: FromDishka[GetBatchProfilesHandler],
    response: Response,
) -> list[PublicProfileDTO]:
    profiles = await handler(
        GetBatchProfilesQuery(user_ids=body.user_ids, viewer_id=viewer_id)
    )
    response.headers["Cache-Control"] = "no-store"
    return profiles


@router.get("/{user_id}")
async def get_public_profile(
    user_id: UUID,
    viewer_id: OptionalViewerId,
    handler: FromDishka[GetPublicProfileHandler],
    response: Response,
) -> PublicProfileDTO:
    profile = await handler(GetPublicProfileQuery(user_id=user_id, viewer_id=viewer_id))
    response.headers["Cache-Control"] = "no-store"
    return profile

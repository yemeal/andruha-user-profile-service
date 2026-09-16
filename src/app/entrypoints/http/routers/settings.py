from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Response

from app.application.commands.settings.update.command import UpdateSettingsCommand
from app.application.dispatching.bus import CommandBusProtocol
from app.application.dto.settings import SettingsDTO
from app.application.queries.settings.get_my.handler import GetMySettingsHandler
from app.application.queries.settings.get_my.query import GetMySettingsQuery
from app.domain.exceptions.user_settings import UserSettingsNotFoundError
from app.entrypoints.http.dependencies import (
    CurrentUserId,
    ExpectedVersion,
    HTTPCommandContext,
)
from app.entrypoints.http.responses import set_private_version
from app.entrypoints.http.schemas import SettingsPatchRequest

router = APIRouter(
    prefix="/api/v1/settings", tags=["settings"], route_class=DishkaRoute
)


@router.get("/me")
async def get_my_settings(
    user_id: CurrentUserId,
    handler: FromDishka[GetMySettingsHandler],
    response: Response,
) -> SettingsDTO:
    try:
        settings = await handler(GetMySettingsQuery(user_id=user_id))
    except UserSettingsNotFoundError as error:
        raise HTTPException(status_code=404, detail="Settings not found") from error
    set_private_version(response, settings.version)
    return settings


@router.patch("/me")
async def patch_my_settings(
    user_id: CurrentUserId,
    version: ExpectedVersion,
    context: HTTPCommandContext,
    body: SettingsPatchRequest,
    commands: FromDishka[CommandBusProtocol],
    response: Response,
) -> SettingsDTO:
    privacy = body.privacy
    try:
        settings = await commands.dispatch(
            UpdateSettingsCommand(
                user_id=user_id,
                expected_version=version,
                theme=body.theme,
                locale=body.locale,
                timezone=body.timezone,
                who_can_see_avatar=privacy.who_can_see_avatar if privacy else None,
                who_can_see_bio=privacy.who_can_see_bio if privacy else None,
                who_can_find_by_username=privacy.who_can_find_by_username
                if privacy
                else None,
            ),
            context,
        )
    except UserSettingsNotFoundError as error:
        raise HTTPException(status_code=404, detail="Settings not found") from error
    set_private_version(response, settings.version)
    return settings

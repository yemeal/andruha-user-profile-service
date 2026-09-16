"""Map HTTP credentials to the viewer identity used by application queries."""

import re
from secrets import compare_digest
from typing import Annotated
from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.dispatching.context import CommandContext
from app.core.settings import InternalAPISettings
from app.entrypoints.http.security import AccessTokenVerifier, InvalidAccessTokenError

bearer = HTTPBearer(auto_error=False)
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


def authentication_required() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Invalid or missing access token",
        headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
    )


@inject
async def optional_viewer_id(
    request: Request,
    credentials: Credentials,
    verifier: FromDishka[AccessTokenVerifier | None],
) -> UUID | None:
    if credentials is None:
        if "authorization" in request.headers:
            raise authentication_required()
        return None
    if verifier is None:
        raise HTTPException(
            status_code=503,
            detail="Authentication unavailable",
            headers={"Cache-Control": "no-store"},
        )
    try:
        return verifier.verify(credentials.credentials)
    except InvalidAccessTokenError as error:
        raise authentication_required() from error


OptionalViewerId = Annotated[UUID | None, Depends(optional_viewer_id)]


def current_user_id(viewer_id: OptionalViewerId) -> UUID:
    if viewer_id is None:
        raise authentication_required()
    return viewer_id


CurrentUserId = Annotated[UUID, Depends(current_user_id)]


def expected_version(if_match: Annotated[str | None, Header()] = None) -> int:
    if if_match is None:
        raise HTTPException(status_code=428, detail="If-Match is required")
    # Only one strong version ETag is supported, within the database bigint range.
    if not re.fullmatch(r'"[1-9][0-9]{0,18}"', if_match):
        raise HTTPException(status_code=400, detail="Invalid version ETag")
    version = int(if_match[1:-1])
    if version > 2**63 - 1:
        raise HTTPException(status_code=400, detail="Invalid version ETag")
    return version


ExpectedVersion = Annotated[int, Depends(expected_version)]


def command_context(
    user_id: CurrentUserId,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=255)],
) -> CommandContext:
    return CommandContext(
        idempotency_key=idempotency_key,
        idempotency_scope=f"user:{user_id}",
        actor_id=str(user_id),
    )


HTTPCommandContext = Annotated[CommandContext, Depends(command_context)]


@inject
async def require_identity_service(
    settings: FromDishka[InternalAPISettings],
    x_service_token: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.token.get_secret_value() if settings.token else None
    if not expected:
        raise HTTPException(
            status_code=503, detail="Service authentication unavailable"
        )
    if x_service_token is None or not compare_digest(
        x_service_token.encode(), expected.encode()
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing service token")

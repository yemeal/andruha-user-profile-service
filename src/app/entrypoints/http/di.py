"""Dishka factories for HTTP authentication."""

from dishka import (
    Provider,
    Scope,
    provide,
)

from app.core.settings import JWTSettings
from app.entrypoints.http.security import AccessTokenVerifier


class HTTPProvider(Provider):
    @provide(scope=Scope.APP)
    def access_token_verifier(
        self, settings: JWTSettings
    ) -> AccessTokenVerifier | None:
        return AccessTokenVerifier(settings) if settings.public_keys else None

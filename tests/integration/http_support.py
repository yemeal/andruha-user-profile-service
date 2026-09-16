"""Real HTTP, Dishka, handlers and command dispatch; only storage ports are fake."""

from collections.abc import Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dishka import Provider, Scope, make_async_container, provide
from fastapi.testclient import TestClient
from pydantic import SecretStr
from tests.unit.application.support import HandlerHarness, ProfileReader, SettingsReader
from tests.unit.idempotency.fakes import DurableStore, HotStore, Session, State, Uow

from app.application.dispatching.bus import CommandBus, CommandBusProtocol
from app.application.dispatching.execution import CommandExecution
from app.application.idempotency.coordinator import IdempotencyCoordinator
from app.application.idempotency.middleware import IdempotencyMiddleware
from app.application.idempotency.transactional_execution import (
    TransactionalIdempotencyExecution,
)
from app.application.ports.persistence.readers.profiles import ProfileReaderProtocol
from app.application.ports.persistence.readers.settings import SettingsReaderProtocol
from app.core.settings import AppSettings, InternalAPISettings, JWTSettings
from app.domain.clock import utc_now
from app.entrypoints.http.di import HTTPProvider
from app.entrypoints.http.main import create_app
from app.infrastructure.di.commands import CommandDependencies, build_command_registry
from app.infrastructure.di.queries import QueriesProvider


class ProfileUow(Uow):
    def __init__(self, session, harness):
        super().__init__(session)
        self.harness = harness

    async def __aenter__(self):
        await super().__aenter__()
        self.profiles = self.harness.profiles._rows.copy()
        self.settings = self.harness.settings._rows.copy()
        return self

    async def __aexit__(self, exc_type, *args):
        if exc_type is not None:
            self.harness.profiles._rows = self.profiles
            self.harness.settings._rows = self.settings
        await super().__aexit__(exc_type, *args)


class HTTPTestProvider(Provider):
    def __init__(self, harness, settings, internal_token="test-service-token"):
        super().__init__()
        self.harness = harness
        self.jwt = settings
        self.state = State()
        self.internal_token = internal_token

    @provide(scope=Scope.APP)
    def app_settings(self) -> AppSettings:
        return AppSettings()

    @provide(scope=Scope.APP)
    def jwt_settings(self) -> JWTSettings:
        return self.jwt

    @provide(scope=Scope.APP)
    def internal_api_settings(self) -> InternalAPISettings:
        return InternalAPISettings(
            token=SecretStr(self.internal_token) if self.internal_token else None
        )

    @provide(scope=Scope.REQUEST)
    def profiles(self) -> ProfileReaderProtocol:
        return ProfileReader(self.harness.profiles)

    @provide(scope=Scope.REQUEST)
    def settings(self) -> SettingsReaderProtocol:
        return SettingsReader(self.harness.settings)

    @provide(scope=Scope.APP)
    def commands(self) -> CommandBusProtocol:
        @asynccontextmanager
        async def scope():
            async with Session(self.state) as session:
                uow = ProfileUow(session, self.harness)
                durable = TransactionalIdempotencyExecution(
                    DurableStore(session, clock=utc_now), uow
                )
                coordinator = IdempotencyCoordinator(HotStore(self.state), durable)
                yield CommandExecution(
                    CommandDependencies(self.harness.profiles, self.harness.settings),
                    uow,
                    IdempotencyMiddleware(coordinator),
                )

        return CommandBus(build_command_registry(), scope)


@dataclass
class Tokens:
    private_key: rsa.RSAPrivateKey
    settings: JWTSettings

    def issue(
        self,
        user_id: UUID,
        *,
        claims=None,
        headers=None,
        omit=None,
        key=None,
        algorithm="RS256",
    ) -> str:
        now = int(datetime.now(UTC).timestamp())
        payload = {
            "iss": self.settings.issuer,
            "aud": self.settings.audience,
            "sub": str(user_id),
            "iat": now,
            "exp": now + 300,
            "jti": str(uuid4()),
            "role": "USER",
            **(claims or {}),
        }
        if omit is not None:
            payload.pop(omit)
        return jwt.encode(
            payload,
            self.private_key if key is None else key,
            algorithm=algorithm,
            headers={"kid": "test-key", "typ": "at+jwt", **(headers or {})},
        )

    def authorization(self, user_id: UUID, **kwargs: Any) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.issue(user_id, **kwargs)}"}

    def mutation(self, user_id: UUID, version=1, key=None) -> dict[str, str]:
        return {
            **self.authorization(user_id),
            "If-Match": f'"{version}"',
            "Idempotency-Key": key or str(uuid4()),
        }


@pytest.fixture(scope="module")
def tokens(tmp_path_factory):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path = tmp_path_factory.mktemp("jwt") / "public.pem"
    path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    return Tokens(key, JWTSettings(public_keys={"test-key": path}))


@pytest.fixture
def harness():
    return HandlerHarness()


@contextmanager
def profile_client(
    harness: HandlerHarness,
    settings: JWTSettings,
    *,
    internal_token="test-service-token",
) -> Iterator[TestClient]:
    container = make_async_container(
        HTTPTestProvider(harness, settings, internal_token),
        QueriesProvider(),
        HTTPProvider(),
    )
    with TestClient(create_app(container)) as client:
        yield client


@pytest.fixture
def client(harness, tokens):
    with profile_client(harness, tokens.settings) as client:
        yield client

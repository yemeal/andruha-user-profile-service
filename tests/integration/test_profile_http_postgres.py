"""HTTP -> Dishka -> command/query -> real PostgreSQL and Valkey."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import httpx2
import pytest
from dishka import Provider, Scope, provide
from pydantic import SecretStr
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.integration.http_support import tokens as tokens
from tests.integration.test_internal_provisioning import BODY, HEADERS
from tests.integration.test_profile_persistence import (
    profile_hot_store as profile_hot_store,
)
from tests.integration.test_profile_persistence import (
    profile_sessions as profile_sessions,
)

from app.application.commands.profiles.create_default.command import (
    CreateDefaultProfileCommand,
)
from app.application.dispatching.bus import CommandBusProtocol
from app.application.dispatching.context import CommandContext
from app.application.dispatching.result_mode import ResultMode
from app.application.exceptions.persistence import PersistenceUnavailableError
from app.application.ports.idempotency.hot_store import HotIdempotencyStore
from app.core.settings import InternalAPISettings, JWTSettings
from app.entrypoints.http.di import HTTPProvider
from app.entrypoints.http.main import create_app
from app.infrastructure.database.models import ProfileORM, SettingsORM
from app.infrastructure.database.repositories.settings import PostgresSettingsRepository
from app.infrastructure.di import create_container

pytestmark = pytest.mark.integration


class LiveOverrides(Provider):
    def __init__(self, sessions, hot, jwt):
        super().__init__()
        self.sessions = sessions
        self.hot = hot
        self.jwt = jwt

    @provide(scope=Scope.APP, override=True)
    def sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        return self.sessions

    @provide(scope=Scope.APP, override=True)
    def hot_store(self) -> HotIdempotencyStore:
        return self.hot

    @provide(scope=Scope.APP, override=True)
    def jwt_settings(self) -> JWTSettings:
        return self.jwt

    @provide(scope=Scope.APP, override=True)
    def internal_api_settings(self) -> InternalAPISettings:
        return InternalAPISettings(token=SecretStr("test-service-token"))


@pytest.fixture
async def live_app(profile_sessions, profile_hot_store, tokens):
    app = create_app(
        create_container(
            HTTPProvider(),
            LiveOverrides(profile_sessions, profile_hot_store, tokens.settings),
        )
    )
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def live_client(live_app):
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=live_app), base_url="http://test"
    ) as client:
        yield client


async def test_live_http_lifecycle_and_durable_replay(
    live_client, profile_sessions, tokens
):
    user_id = uuid4()
    headers = tokens.authorization(user_id)
    assert (
        await live_client.head(f"/internal/v1/profiles/{user_id}")
    ).status_code == 404
    assert (
        await live_client.get("/api/v1/profiles/me", headers=headers)
    ).status_code == 404
    assert (
        await live_client.put(
            f"/internal/v1/profiles/{user_id}", headers=HEADERS, json=BODY
        )
    ).status_code == 204
    own = await live_client.get("/api/v1/profiles/me", headers=headers)
    assert own.status_code == 200 and own.json()["version"] == 1
    mutation = tokens.mutation(user_id)
    payload = {"username": "live_user", "bio": "Private biography"}
    changed = await live_client.patch(
        "/api/v1/profiles/me", headers=mutation, json=payload
    )
    assert changed.status_code == 200 and changed.json()["version"] == 2
    replay = await live_client.patch(
        "/api/v1/profiles/me", headers=mutation, json=payload
    )
    assert replay.status_code == 200 and replay.json() == changed.json()
    assert (
        await live_client.get("/api/v1/profiles?username=LIVE_USER")
    ).status_code == 200
    hidden = await live_client.patch(
        "/api/v1/settings/me",
        headers=tokens.mutation(user_id),
        json={
            "privacy": {
                "who_can_see_bio": "NOBODY",
                "who_can_find_by_username": "NOBODY",
            }
        },
    )
    assert hidden.status_code == 200
    assert (
        await live_client.get("/api/v1/profiles?username=live_user")
    ).status_code == 404
    public = await live_client.post(
        "/api/v1/profiles/batch",
        json={"user_ids": [str(uuid4()), str(user_id), str(user_id)]},
    )
    assert public.status_code == 200 and len(public.json()) == 1
    assert public.json()[0]["bio"] is None
    assert (
        await live_client.head(f"/internal/v1/profiles/{user_id}")
    ).status_code == 200
    async with profile_sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ProfileORM)) == 1
        assert await session.scalar(select(func.count()).select_from(SettingsORM)) == 1


async def test_concurrent_provisioning_and_conditional_writes(live_client, tokens):
    user_id = uuid4()
    auth = tokens.authorization(user_id)
    provisioned = await asyncio.gather(
        *(
            live_client.put(
                f"/internal/v1/profiles/{user_id}", headers=HEADERS, json=BODY
            )
            for _ in range(4)
        )
    )
    assert all(response.status_code in {204, 409} for response in provisioned)
    assert any(response.status_code == 204 for response in provisioned)
    assert (
        await live_client.put(
            f"/internal/v1/profiles/{user_id}", headers=HEADERS, json=BODY
        )
    ).status_code == 204
    assert (await live_client.get("/api/v1/profiles/me", headers=auth)).json()[
        "version"
    ] == 1
    writes = await asyncio.gather(
        *(
            live_client.patch(
                "/api/v1/profiles/me",
                headers=tokens.mutation(user_id),
                json={"bio": bio},
            )
            for bio in ("first", "second")
        )
    )
    assert sorted(response.status_code for response in writes) == [200, 409]
    result = await live_client.get("/api/v1/profiles/me", headers=auth)
    assert result.json()["version"] == 2


async def test_provisioning_rolls_back_profile_when_settings_fail(
    live_client, profile_sessions, monkeypatch
):
    async def fail(*args, **kwargs):
        raise PersistenceUnavailableError("private storage details")

    monkeypatch.setattr(PostgresSettingsRepository, "create_default_if_absent", fail)
    response = await live_client.put(
        f"/internal/v1/profiles/{uuid4()}", headers=HEADERS, json=BODY
    )
    assert response.status_code == 503
    assert "private storage details" not in response.text
    async with profile_sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ProfileORM)) == 0
        assert await session.scalar(select(func.count()).select_from(SettingsORM)) == 0


async def test_registration_replay_preserves_updates_and_reads_do_not_repair(
    live_client, live_app, profile_sessions, tokens
):
    user_id = uuid4()
    auth = tokens.authorization(user_id)
    assert (
        await live_client.put(
            f"/internal/v1/profiles/{user_id}", headers=HEADERS, json=BODY
        )
    ).status_code == 204
    changed = await live_client.patch(
        "/api/v1/profiles/me",
        headers=tokens.mutation(user_id),
        json={"display_name": "Keep Name"},
    )
    assert changed.status_code == 200
    bus = await live_app.state.dishka_container.get(CommandBusProtocol)
    await bus.dispatch(
        CreateDefaultProfileCommand(
            user_id=user_id, registered_at=datetime(2020, 1, 1, tzinfo=UTC)
        ),
        CommandContext(idempotency_key=str(uuid4()), idempotency_scope="registration"),
        result_mode=ResultMode.COMPLETION_ONLY,
    )
    assert (
        await live_client.put(
            f"/internal/v1/profiles/{user_id}", headers=HEADERS, json=BODY
        )
    ).status_code == 204
    async with profile_sessions.begin() as session:
        await session.execute(delete(SettingsORM).where(SettingsORM.user_id == user_id))
    response = await live_client.get("/api/v1/settings/me", headers=auth)
    assert response.status_code == 404
    own = await live_client.get("/api/v1/profiles/me", headers=auth)
    assert own.json()["display_name"] == "Keep Name" and own.json()["version"] == 2

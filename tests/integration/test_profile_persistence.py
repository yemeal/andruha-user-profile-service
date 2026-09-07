"""Real PostgreSQL tests using an isolated schema migrated from the baseline."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from redis.asyncio import Redis
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.commands.profiles.create_default.command import (
    CreateDefaultProfileCommand,
)
from app.application.commands.profiles.create_default.handler import (
    CreateDefaultProfileHandler,
)
from app.application.commands.profiles.update.command import UpdateProfileCommand
from app.application.commands.settings.update.command import UpdateSettingsCommand
from app.application.dispatching.context import CommandContext
from app.application.dispatching.result_mode import ResultMode
from app.application.dto import ProfileDTO
from app.application.exceptions.idempotency import (
    IdempotencyConflictError,
    IdempotencyUnavailableError,
)
from app.application.idempotency.policy import IdempotencyMode, IdempotencyPolicy
from app.domain.aggregates.profiles import UserProfile
from app.domain.aggregates.settings import UserSettings
from app.domain.exceptions.user_profile import (
    ProfileVersionMismatchError,
    UsernameAlreadyTakenError,
)
from app.domain.exceptions.user_settings import SettingsVersionMismatchError
from app.infrastructure.database.models import (
    ProfileORM,
    SettingsORM,
)
from app.infrastructure.database.readers import (
    PostgresProfileReader,
    PostgresSettingsReader,
)
from app.infrastructure.database.repositories import (
    PostgresProfileRepository,
    PostgresSettingsRepository,
)
from app.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.di.profiles import build_profile_command_bus
from app.infrastructure.idempotency.postgres.models import IdempotencyRecordORM
from app.infrastructure.idempotency.redis.hot_store import RedisHotIdempotencyStore

pytestmark = pytest.mark.integration
NOW = datetime(2026, 9, 7, 10, tzinfo=UTC)


def migration_config(connection):
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


@pytest.fixture
async def profile_sessions():
    dsn = os.getenv("TEST_PROFILE_POSTGRES_DSN")
    if not dsn:
        if os.getenv("REQUIRE_INFRASTRUCTURE_TESTS"):
            pytest.fail("TEST_PROFILE_POSTGRES_DSN must be configured")
        pytest.skip("TEST_PROFILE_POSTGRES_DSN is not configured")
    schema = "profile_test_" + uuid4().hex
    admin = create_async_engine(dsn)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        dsn,
        isolation_level="READ COMMITTED",
        connect_args={
            "server_settings": {"search_path": schema},
            "command_timeout": 15,
        },
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync: command.upgrade(migration_config(sync), "head")
            )
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


@pytest.fixture
async def profile_hot_store():
    url = os.getenv("TEST_IDEMPOTENCY_REDIS_URL")
    if not url:
        if os.getenv("REQUIRE_INFRASTRUCTURE_TESTS"):
            pytest.fail("TEST_IDEMPOTENCY_REDIS_URL must be configured")
        pytest.skip("TEST_IDEMPOTENCY_REDIS_URL is not configured")
    client = Redis.from_url(url)
    namespace = "profile-persistence-test:" + uuid4().hex
    try:
        yield RedisHotIdempotencyStore(client, key_namespace=namespace)
    finally:
        async for key in client.scan_iter(match=namespace + ":*"):
            await client.delete(key)
        await client.aclose()


async def provision(sessions, user_id):
    async with sessions() as session, SqlAlchemyUnitOfWork(session):
        handler = CreateDefaultProfileHandler(
            PostgresProfileRepository(session), PostgresSettingsRepository(session)
        )
        await handler(CreateDefaultProfileCommand(user_id=user_id, registered_at=NOW))


async def test_migration_roundtrip_and_schema_match(profile_sessions):
    async with profile_sessions() as session:
        connection = await session.connection()
        tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
        assert set(tables) == {
            "alembic_version",
            "profiles",
            "user_settings",
            "idempotency_records",
        }
        await connection.run_sync(
            lambda sync: command.downgrade(migration_config(sync), "base")
        )
        assert await connection.run_sync(
            lambda sync: inspect(sync).get_table_names()
        ) == ["alembic_version"]
        await connection.run_sync(
            lambda sync: command.upgrade(migration_config(sync), "head")
        )
        await session.commit()


async def test_concurrent_provision_and_late_event_preserve_edits(profile_sessions):
    user_id = uuid4()
    async with asyncio.timeout(15):
        await asyncio.gather(*(provision(profile_sessions, user_id) for _ in range(6)))
    async with profile_sessions() as session, SqlAlchemyUnitOfWork(session):
        repo = PostgresProfileRepository(session)
        profile = await repo.get_by_id(user_id)
        profile.update_profile(display_name="Changed", now=NOW + timedelta(seconds=1))
        await repo.update(profile, expected_version=1)
    await provision(profile_sessions, user_id)
    async with profile_sessions() as session, SqlAlchemyUnitOfWork(session):
        assert await session.scalar(select(func.count()).select_from(ProfileORM)) == 1
        assert await session.scalar(select(func.count()).select_from(SettingsORM)) == 1
        profile = await PostgresProfileRepository(session).get_by_id(user_id)
        assert profile.display_name == "Changed" and profile.version == 2
        assert profile.created_at == NOW


async def test_failure_creating_settings_rolls_back_profile(profile_sessions):
    user_id = uuid4()

    class FailingSettings(PostgresSettingsRepository):
        async def create_default_if_absent(self, user_id, now):
            raise RuntimeError("settings unavailable")

    async with profile_sessions() as session:
        with pytest.raises(RuntimeError, match="settings unavailable"):
            async with SqlAlchemyUnitOfWork(session):
                await CreateDefaultProfileHandler(
                    PostgresProfileRepository(session), FailingSettings(session)
                )(CreateDefaultProfileCommand(user_id=user_id, registered_at=NOW))
        async with SqlAlchemyUnitOfWork(session):
            assert not await PostgresProfileRepository(session).exists(user_id)


@pytest.mark.parametrize("missing_half", ["profile", "settings"])
async def test_provision_repairs_missing_half_without_reset(
    profile_sessions, missing_half
):
    user_id = uuid4()
    await provision(profile_sessions, user_id)
    async with profile_sessions() as session, SqlAlchemyUnitOfWork(session):
        repo = (
            PostgresProfileRepository(session)
            if missing_half == "profile"
            else PostgresSettingsRepository(session)
        )
        assert await repo.delete(user_id)
    await provision(profile_sessions, user_id)
    async with profile_sessions() as session, SqlAlchemyUnitOfWork(session):
        assert await PostgresProfileRepository(session).exists(user_id)
        assert await PostgresSettingsRepository(session).exists(user_id)


@pytest.mark.parametrize("kind", ["profile", "settings"])
async def test_real_optimistic_race_has_one_winner(profile_sessions, kind):
    user_id = uuid4()
    await provision(profile_sessions, user_id)
    barrier = asyncio.Barrier(2)

    async def write(value):
        async with profile_sessions() as session, SqlAlchemyUnitOfWork(session):
            repo = (
                PostgresProfileRepository(session)
                if kind == "profile"
                else PostgresSettingsRepository(session)
            )
            aggregate = await repo.get_by_id(user_id)
            if kind == "profile":
                aggregate.update_profile(
                    display_name=value, now=NOW + timedelta(seconds=1)
                )
            else:
                aggregate.update_settings(theme=value, now=NOW + timedelta(seconds=1))
            await barrier.wait()
            return await repo.update(aggregate, expected_version=1)

    async with asyncio.timeout(15):
        results = await asyncio.gather(
            write("First" if kind == "profile" else "dark"),
            write("Second" if kind == "profile" else "light"),
            return_exceptions=True,
        )
    error_type = (
        ProfileVersionMismatchError
        if kind == "profile"
        else SettingsVersionMismatchError
    )
    assert sum(isinstance(result, error_type) for result in results) == 1
    winner = next(result for result in results if not isinstance(result, Exception))
    async with profile_sessions() as session, SqlAlchemyUnitOfWork(session):
        repo = (
            PostgresProfileRepository(session)
            if kind == "profile"
            else PostgresSettingsRepository(session)
        )
        assert await repo.get_by_id(user_id) == winner
        assert winner.version == 2


async def test_username_uniqueness_is_enforced_by_database(profile_sessions):
    ids = [uuid4(), uuid4()]
    await asyncio.gather(*(provision(profile_sessions, uid) for uid in ids))
    barrier = asyncio.Barrier(2)

    async def take(uid, username):
        async with profile_sessions() as session, SqlAlchemyUnitOfWork(session):
            repo = PostgresProfileRepository(session)
            aggregate = await repo.get_by_id(uid)
            aggregate.update_profile(username=username, now=NOW + timedelta(seconds=1))
            await barrier.wait()
            return await repo.update(aggregate, expected_version=1)

    async with asyncio.timeout(15):
        results = await asyncio.gather(
            take(ids[0], "Shared"), take(ids[1], "shared"), return_exceptions=True
        )
    assert sum(isinstance(result, UsernameAlreadyTakenError) for result in results) == 1
    async with profile_sessions() as session, SqlAlchemyUnitOfWork(session):
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProfileORM)
                .where(ProfileORM.username == "shared")
            )
            == 1
        )


async def test_readers_return_detached_values_and_preserve_code_contract(
    profile_sessions,
):
    user_id = uuid4()
    async with profile_sessions() as session, SqlAlchemyUnitOfWork(session):
        profile = UserProfile.create_default(user_id, NOW)
        profile.update_profile(
            username="alice", bio="x" * 255, now=NOW + timedelta(seconds=1)
        )
        profile.update_avatar(
            avatar_key="any/string/key", now=NOW + timedelta(seconds=2)
        )
        await PostgresProfileRepository(session).create(profile)
        settings = UserSettings.create_default(user_id, NOW)
        settings.update_settings(locale="en", now=NOW + timedelta(seconds=1))
        await PostgresSettingsRepository(session).create(settings)
    async with profile_sessions() as session, SqlAlchemyUnitOfWork(session):
        reader = PostgresProfileReader(session)
        loaded = await reader.get_by_username("ALICE")
        assert loaded == profile
        loaded.update_profile(bio="local edit", now=NOW + timedelta(seconds=3))
        assert (await reader.get_by_id(user_id)).bio == "x" * 255
        assert await reader.get_batch([]) == []
        assert await reader.get_batch([user_id, uuid4()]) == [profile]
        assert await PostgresSettingsReader(session).get_by_id(user_id) == settings
        assert not hasattr(reader, "update")


async def test_actual_commands_commit_and_replay_from_postgres_after_cache_loss(
    profile_sessions, profile_hot_store
):
    bus = build_profile_command_bus(
        profile_sessions,
        hot_store=profile_hot_store,
        mutation_policy=IdempotencyPolicy(),
        provisioning_policy=IdempotencyPolicy(),
        clock=lambda: NOW + timedelta(seconds=2),
    )
    user_id = uuid4()
    await provision(profile_sessions, user_id)
    ctx = CommandContext(idempotency_key="update", idempotency_scope=f"user:{user_id}")
    change = UpdateProfileCommand(
        user_id=user_id, expected_version=1, display_name="Saved"
    )
    first = await bus.dispatch(change, ctx)
    assert isinstance(first, ProfileDTO) and first.version == 2

    # Use a documented failure mode rather than leaking keys into another namespace.
    class OfflineHot:
        async def claim(self, *args):
            raise IdempotencyUnavailableError("offline")

    replay_bus = build_profile_command_bus(
        profile_sessions,
        hot_store=OfflineHot(),
        mutation_policy=IdempotencyPolicy(),
        provisioning_policy=IdempotencyPolicy(),
        clock=lambda: NOW + timedelta(seconds=2),
    )
    assert await replay_bus.dispatch(change, ctx) == first
    with pytest.raises(IdempotencyConflictError):
        await replay_bus.dispatch(
            change.model_copy(update={"display_name": "Other"}), ctx
        )
    settings_ctx = CommandContext(
        idempotency_key="settings", idempotency_scope=f"user:{user_id}"
    )
    settings = await bus.dispatch(
        UpdateSettingsCommand(user_id=user_id, expected_version=1, theme="dark"),
        settings_ctx,
    )
    assert settings.version == 2
    async with profile_sessions() as session, SqlAlchemyUnitOfWork(session):
        assert (
            await PostgresProfileRepository(session).get_by_id(user_id)
        ).version == 2
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyRecordORM))
            == 2
        )


@pytest.mark.parametrize(
    "privacy",
    [
        {},
        {
            "who_can_see_avatar": None,
            "who_can_find_by_username": "ALL",
            "who_can_see_bio": "ALL",
        },
        {
            "who_can_see_avatar": "ALL",
            "who_can_find_by_username": "ALL",
            "who_can_see_bio": "ALL",
            "extra": "ALL",
        },
    ],
)
async def test_database_rejects_invalid_privacy(profile_sessions, privacy):
    user_id = uuid4()
    await provision(profile_sessions, user_id)
    async with profile_sessions() as session:
        with pytest.raises(IntegrityError):
            async with SqlAlchemyUnitOfWork(session):
                await session.execute(
                    SettingsORM.__table__.update()
                    .where(SettingsORM.user_id == user_id)
                    .values(privacy=privacy)
                )


async def test_same_command_race_without_hot_store_returns_committed_replay(
    profile_sessions, monkeypatch
):
    class OfflineHot:
        async def claim(self, *args):
            raise IdempotencyUnavailableError("offline")

    user_id = uuid4()
    await provision(profile_sessions, user_id)
    barrier = asyncio.Barrier(2)
    original = PostgresProfileRepository.get_by_id
    reads = 0

    async def concurrent_read(self, entity_id):
        nonlocal reads
        result = await original(self, entity_id)
        reads += 1
        if reads <= 2:
            await barrier.wait()
        return result

    monkeypatch.setattr(PostgresProfileRepository, "get_by_id", concurrent_read)
    bus = build_profile_command_bus(
        profile_sessions,
        hot_store=OfflineHot(),
        mutation_policy=IdempotencyPolicy(),
        provisioning_policy=IdempotencyPolicy(),
        clock=lambda: NOW + timedelta(seconds=1),
    )
    change = UpdateProfileCommand(
        user_id=user_id, expected_version=1, display_name="Winner"
    )
    ctx = CommandContext(idempotency_key="same", idempotency_scope=f"user:{user_id}")
    async with asyncio.timeout(15):
        results = await asyncio.gather(
            bus.dispatch(change, ctx), bus.dispatch(change, ctx), return_exceptions=True
        )
    assert all(isinstance(result, ProfileDTO) for result in results), results
    assert results[0] == results[1]
    async with profile_sessions() as session, SqlAlchemyUnitOfWork(session):
        assert (
            await original(PostgresProfileRepository(session), user_id)
        ).version == 2
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyRecordORM))
            == 1
        )


@pytest.mark.parametrize("kind", ["profile", "settings"])
async def test_stale_new_key_preserves_conflict_and_does_not_store_replay(
    profile_sessions, profile_hot_store, kind
):
    user_id = uuid4()
    await provision(profile_sessions, user_id)
    bus = build_profile_command_bus(
        profile_sessions,
        hot_store=profile_hot_store,
        mutation_policy=IdempotencyPolicy(),
        provisioning_policy=IdempotencyPolicy(),
        clock=lambda: NOW + timedelta(seconds=1),
    )
    change = (
        UpdateProfileCommand(user_id=user_id, expected_version=1, display_name="Saved")
        if kind == "profile"
        else UpdateSettingsCommand(user_id=user_id, expected_version=1, theme="dark")
    )
    scope = f"user:{user_id}"
    await bus.dispatch(
        change, CommandContext(idempotency_key="first", idempotency_scope=scope)
    )
    error = (
        ProfileVersionMismatchError
        if kind == "profile"
        else SettingsVersionMismatchError
    )
    with pytest.raises(error):
        await bus.dispatch(
            change, CommandContext(idempotency_key="new", idempotency_scope=scope)
        )
    async with profile_sessions() as session, SqlAlchemyUnitOfWork(session):
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyRecordORM))
            == 1
        )


async def test_bus_rolls_back_update_when_replay_cannot_be_saved(
    profile_sessions, profile_hot_store, monkeypatch
):
    from app.infrastructure.idempotency.postgres.durable_store import (
        PostgresDurableIdempotencyStore,
    )

    user_id = uuid4()
    await provision(profile_sessions, user_id)

    async def fail(self, identity, completed):
        raise RuntimeError("replay failed")

    monkeypatch.setattr(PostgresDurableIdempotencyStore, "try_add_completed", fail)
    bus = build_profile_command_bus(
        profile_sessions,
        hot_store=profile_hot_store,
        mutation_policy=IdempotencyPolicy(),
        provisioning_policy=IdempotencyPolicy(),
        clock=lambda: NOW + timedelta(seconds=1),
    )
    with pytest.raises(RuntimeError, match="replay failed"):
        await bus.dispatch(
            UpdateProfileCommand(
                user_id=user_id, expected_version=1, display_name="Lost"
            ),
            CommandContext(
                idempotency_key="failure", idempotency_scope=f"user:{user_id}"
            ),
        )
    async with profile_sessions() as session, SqlAlchemyUnitOfWork(session):
        profile = await PostgresProfileRepository(session).get_by_id(user_id)
        assert profile.version == 1 and profile.display_name == "Пользователь"
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyRecordORM))
            == 0
        )


async def test_all_registered_mutations_and_noop_versions(
    profile_sessions, profile_hot_store
):
    from app.application.commands.profiles.update_avatar.command import (
        UpdateAvatarCommand,
    )
    from app.application.commands.settings.reset.command import ResetSettingsCommand

    user_id = uuid4()
    bus = build_profile_command_bus(
        profile_sessions,
        hot_store=profile_hot_store,
        mutation_policy=IdempotencyPolicy(),
        provisioning_policy=IdempotencyPolicy(),
        clock=lambda: NOW + timedelta(seconds=1),
    )
    await provision(profile_sessions, user_id)

    async def dispatch(command):
        return await bus.dispatch(
            command,
            CommandContext(
                idempotency_key=uuid4().hex, idempotency_scope=f"user:{user_id}"
            ),
        )

    profile = await dispatch(
        UpdateAvatarCommand(
            user_id=user_id, expected_version=1, avatar_key="avatars/owned"
        )
    )
    assert profile.version == 2 and profile.avatar_key == "avatars/owned"
    same = await dispatch(
        UpdateAvatarCommand(
            user_id=user_id, expected_version=2, avatar_key="avatars/owned"
        )
    )
    assert same.version == 2
    deleted = await dispatch(
        UpdateAvatarCommand(user_id=user_id, expected_version=2, avatar_key=None)
    )
    assert deleted.version == 3 and deleted.avatar_key is None
    settings = await dispatch(
        UpdateSettingsCommand(
            user_id=user_id, expected_version=1, theme="dark", who_can_see_bio="NOBODY"
        )
    )
    assert settings.version == 2
    reset = await dispatch(ResetSettingsCommand(user_id=user_id, expected_version=2))
    assert reset.version == 3 and reset.theme == "system"
    assert reset.privacy.who_can_see_bio == "ALL"
    same_reset = await dispatch(
        ResetSettingsCommand(user_id=user_id, expected_version=3)
    )
    assert same_reset.version == 3


@pytest.mark.parametrize("kind", ["profile", "settings"])
async def test_repository_missing_and_transaction_contract(profile_sessions, kind):
    from app.domain.exceptions.user_profile import UserProfileNotFoundError
    from app.domain.exceptions.user_settings import UserSettingsNotFoundError

    async with profile_sessions() as session:
        repo = (
            PostgresProfileRepository(session)
            if kind == "profile"
            else PostgresSettingsRepository(session)
        )
        aggregate = (UserProfile if kind == "profile" else UserSettings).create_default(
            uuid4(), NOW
        )
        with pytest.raises(RuntimeError, match="transaction"):
            await repo.create(aggregate)
        with pytest.raises(
            UserProfileNotFoundError if kind == "profile" else UserSettingsNotFoundError
        ):
            async with SqlAlchemyUnitOfWork(session):
                await repo.update(aggregate, expected_version=1)
        async with SqlAlchemyUnitOfWork(session):
            assert not await repo.delete(aggregate.id)
            assert await repo.get_by_id(aggregate.id) is None


async def test_runtime_read_scope_is_enforced_read_only(profile_sessions, monkeypatch):
    from sqlalchemy.exc import DBAPIError

    from app.infrastructure.database.config import DatabaseSettings
    from app.infrastructure.database.runtime import ProfileDatabase

    database = ProfileDatabase(
        DatabaseSettings(database_url=os.environ["TEST_PROFILE_POSTGRES_DSN"])
    )
    # Route the runtime scope to this test's migrated schema.
    database.sessions = profile_sessions
    try:
        await database.check_ready()
        async with database.readers() as readers:
            assert await readers.profiles.get_by_id(uuid4()) is None
        original = PostgresProfileReader.get_by_id

        async def unexpected_write(self, user_id):
            await self._session.execute(
                text("UPDATE profiles SET display_name=display_name WHERE user_id=:id"),
                {"id": user_id},
            )
            return await original(self, user_id)

        monkeypatch.setattr(PostgresProfileReader, "get_by_id", unexpected_write)
        with pytest.raises(DBAPIError):
            async with database.readers() as readers:
                await readers.profiles.get_by_id(uuid4())
    finally:
        await database.close()


class OfflineRegistrationHot:
    async def claim(self, *args):
        raise IdempotencyUnavailableError("offline")


def registration_context(event_id, consumer="profile.user_registered.v1"):
    return CommandContext(
        idempotency_key=str(event_id), idempotency_scope=f"consumer:{consumer}"
    )


@pytest.mark.parametrize("failure", ["settings", "completion"])
async def test_registration_rollback_retry_and_completion_replay(
    profile_sessions, profile_hot_store, monkeypatch, failure
):
    from app.infrastructure.idempotency.postgres.durable_store import (
        PostgresDurableIdempotencyStore,
    )

    bus = build_profile_command_bus(
        profile_sessions,
        hot_store=profile_hot_store,
        mutation_policy=IdempotencyPolicy(),
        provisioning_policy=IdempotencyPolicy(),
        clock=lambda: NOW,
    )
    registration = CreateDefaultProfileCommand(user_id=uuid4(), registered_at=NOW)
    context = registration_context(uuid4())
    target, method = (
        (PostgresSettingsRepository, "create_default_if_absent")
        if failure == "settings"
        else (PostgresDurableIdempotencyStore, "try_add_completed")
    )

    async def fail(*args, **kwargs):
        raise RuntimeError("injected failure")

    with monkeypatch.context() as patch:
        patch.setattr(target, method, fail)
        with pytest.raises(RuntimeError, match="injected failure"):
            await bus.dispatch(
                registration, context, result_mode=ResultMode.COMPLETION_ONLY
            )
    async with profile_sessions() as session:
        for table in (ProfileORM, SettingsORM, IdempotencyRecordORM):
            assert await session.scalar(select(func.count()).select_from(table)) == 0
    assert (
        await bus.dispatch(
            registration, context, result_mode=ResultMode.COMPLETION_ONLY
        )
        is None
    )
    async with profile_sessions() as session:
        for table in (ProfileORM, SettingsORM, IdempotencyRecordORM):
            assert await session.scalar(select(func.count()).select_from(table)) == 1
        record = (await session.scalars(select(IdempotencyRecordORM))).one()
        assert record.result_type == "completion" and record.result_payload is None
        assert record.resource_id is None and record.resource_type is None
        assert record.subject_id == context.idempotency_scope
        assert record.operation == "profile.create_default.v1"

    # Both hot replay and PostgreSQL fallback must avoid the handler entirely.
    monkeypatch.setattr(CreateDefaultProfileHandler, "__call__", fail)
    assert (
        await bus.dispatch(
            registration, context, result_mode=ResultMode.COMPLETION_ONLY
        )
        is None
    )
    offline_bus = build_profile_command_bus(
        profile_sessions,
        hot_store=OfflineRegistrationHot(),
        mutation_policy=IdempotencyPolicy(),
        provisioning_policy=IdempotencyPolicy(),
        clock=lambda: NOW,
    )
    assert (
        await offline_bus.dispatch(
            registration, context, result_mode=ResultMode.COMPLETION_ONLY
        )
        is None
    )


async def test_registration_concurrent_duplicates_use_one_completion(
    profile_sessions, monkeypatch
):
    barrier = asyncio.Barrier(4)
    original = CreateDefaultProfileHandler.__call__

    async def concurrent_start(self, command):
        await barrier.wait()
        return await original(self, command)

    monkeypatch.setattr(CreateDefaultProfileHandler, "__call__", concurrent_start)
    bus = build_profile_command_bus(
        profile_sessions,
        hot_store=OfflineRegistrationHot(),
        mutation_policy=IdempotencyPolicy(),
        provisioning_policy=IdempotencyPolicy(),
        clock=lambda: NOW,
    )
    registration = CreateDefaultProfileCommand(user_id=uuid4(), registered_at=NOW)
    context = registration_context(uuid4())
    async with asyncio.timeout(15):
        results = await asyncio.gather(
            *(
                bus.dispatch(
                    registration, context, result_mode=ResultMode.COMPLETION_ONLY
                )
                for _ in range(4)
            )
        )
    assert results == [None] * 4
    async with profile_sessions() as session:
        for table in (ProfileORM, SettingsORM, IdempotencyRecordORM):
            assert await session.scalar(select(func.count()).select_from(table)) == 1


async def test_registration_scope_fingerprint_and_retention(
    profile_sessions, monkeypatch
):
    now = NOW
    policy = IdempotencyPolicy(retention_seconds=60, hot_cache_seconds=30)
    bus = build_profile_command_bus(
        profile_sessions,
        hot_store=OfflineRegistrationHot(),
        mutation_policy=IdempotencyPolicy(),
        provisioning_policy=policy,
        clock=lambda: now,
    )
    user_id, event_id = uuid4(), uuid4()
    registration = CreateDefaultProfileCommand(user_id=user_id, registered_at=NOW)
    context = registration_context(event_id)
    await bus.dispatch(registration, context, result_mode=ResultMode.COMPLETION_ONLY)
    with pytest.raises(IdempotencyConflictError):
        await bus.dispatch(
            registration.model_copy(update={"user_id": uuid4()}),
            context,
            result_mode=ResultMode.COMPLETION_ONLY,
        )
    await bus.dispatch(
        registration,
        registration_context(event_id, "other-consumer"),
        result_mode=ResultMode.COMPLETION_ONLY,
    )
    async with profile_sessions() as session, SqlAlchemyUnitOfWork(session):
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyRecordORM))
            == 2
        )
        profiles = PostgresProfileRepository(session)
        profile = await profiles.get_by_id(user_id)
        profile.update_profile(display_name="Preserved", now=NOW + timedelta(seconds=1))
        await profiles.update(profile, expected_version=1)
        settings = PostgresSettingsRepository(session)
        value = await settings.get_by_id(user_id)
        value.update_settings(theme="dark", now=NOW + timedelta(seconds=1))
        await settings.update(value, expected_version=1)
    calls = 0
    original = CreateDefaultProfileHandler.__call__

    async def track(self, command):
        nonlocal calls
        calls += 1
        return await original(self, command)

    monkeypatch.setattr(CreateDefaultProfileHandler, "__call__", track)
    now = NOW + timedelta(seconds=61)
    await bus.dispatch(registration, context, result_mode=ResultMode.COMPLETION_ONLY)
    assert calls == 1
    async with profile_sessions() as session, SqlAlchemyUnitOfWork(session):
        profile = await PostgresProfileRepository(session).get_by_id(user_id)
        settings = await PostgresSettingsRepository(session).get_by_id(user_id)
        assert profile.display_name == "Preserved" and profile.version == 2
        assert settings.theme == "dark" and settings.version == 2
        assert profile.created_at == NOW and settings.created_at == NOW
        record = (
            await session.scalars(
                select(IdempotencyRecordORM).where(
                    IdempotencyRecordORM.subject_id == context.idempotency_scope
                )
            )
        ).one()
        assert record.completed_at == now and record.expires_at == now + timedelta(
            seconds=60
        )


def test_registration_requires_durable_policy():
    with pytest.raises(ValueError, match="HOT_DURABLE"):
        build_profile_command_bus(
            async_sessionmaker(),
            hot_store=OfflineRegistrationHot(),
            mutation_policy=IdempotencyPolicy(),
            provisioning_policy=IdempotencyPolicy(mode=IdempotencyMode.HOT_ONLY),
        )

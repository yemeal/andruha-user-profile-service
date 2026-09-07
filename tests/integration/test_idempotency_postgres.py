"""Real PostgreSQL regressions; set TEST_IDEMPOTENCY_POSTGRES_DSN.

Each test owns a unique schema and drops only that schema.
"""

import asyncio
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.idempotency.models import (
    CompletedIdempotencyResult,
    ExecutionStatus,
    IdempotencyKey,
    StoredResult,
)
from app.application.idempotency.transactional_execution import (
    TransactionalIdempotencyExecution,
)
from app.domain.clock import utc_now
from app.infrastructure.idempotency.postgres.durable_store import (
    PostgresDurableIdempotencyStore,
)
from app.infrastructure.idempotency.postgres.models import IdempotencyRecordORM

pytestmark = pytest.mark.integration


@pytest.fixture
async def sessions():
    dsn = os.getenv("TEST_IDEMPOTENCY_POSTGRES_DSN")
    if not dsn:
        if os.getenv("REQUIRE_INFRASTRUCTURE_TESTS"):
            pytest.fail("TEST_IDEMPOTENCY_POSTGRES_DSN must be configured")
        pytest.skip("TEST_IDEMPOTENCY_POSTGRES_DSN is not configured")
    schema = "idempotency_test_" + uuid4().hex
    admin = create_async_engine(dsn)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        dsn, connect_args={"server_settings": {"search_path": schema}}
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(IdempotencyRecordORM.__table__.create)
            await connection.execute(
                text(
                    "CREATE TABLE effects (id integer PRIMARY KEY, value text NOT NULL)"
                )
            )
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


class SessionUOW:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        self.transaction = await self.session.begin()
        return self

    async def __aexit__(self, *args):
        await self.transaction.__aexit__(*args)


def identity():
    return IdempotencyKey(subject_id="actor", operation="update", key_digest=b"k" * 32)


def completed(value):
    return CompletedIdempotencyResult(
        request_fingerprint=b"f" * 32,
        result_type="dict",
        result_payload={"value": value},
        expires_at=utc_now() + timedelta(seconds=3600),
    )


async def test_expired_row_can_be_replaced_without_cleanup(sessions):
    async with sessions() as session:
        store = PostgresDurableIdempotencyStore(session)
        async with session.begin():
            assert await store.try_add_completed(identity(), completed("old"))
        async with session.begin():
            past = utc_now() - timedelta(days=1)
            await session.execute(
                update(IdempotencyRecordORM).values(
                    created_at=past - timedelta(seconds=2),
                    completed_at=past - timedelta(seconds=1),
                    expires_at=past,
                )
            )
        async with session.begin():
            assert await store.get_completed(identity()) is None
            assert await store.try_add_completed(identity(), completed("new"))
        async with session.begin():
            assert not await store.try_add_completed(identity(), completed("duplicate"))
            assert (await store.get_completed(identity())).result_payload == {
                "value": "new"
            }


async def test_concurrent_attempts_commit_only_winners_local_effect(sessions):
    barrier = asyncio.Barrier(2)

    async def attempt(number):
        async with sessions() as session:
            execution = TransactionalIdempotencyExecution(
                PostgresDurableIdempotencyStore(session), SessionUOW(session)
            )

            async def operation():
                await session.execute(
                    text("INSERT INTO effects VALUES (:id, :value)"),
                    {"id": number, "value": str(number)},
                )
                await barrier.wait()
                return StoredResult(result_type="int", result_payload={"value": number})

            return await execution.execute_once(
                identity(), b"f" * 32, operation, retention_seconds=3600
            )

    async with asyncio.timeout(15):
        left, right = await asyncio.gather(attempt(1), attempt(2))
    assert {left.status, right.status} == {
        ExecutionStatus.EXECUTED,
        ExecutionStatus.REPLAY,
    }
    assert left.completed == right.completed
    async with sessions() as session:
        rows = (await session.execute(text("SELECT id FROM effects"))).scalars().all()
    assert rows == [left.completed.result_payload["value"]]


async def test_production_bus_scope_commits_one_winner_for_concurrent_commands(
    sessions,
):
    from pydantic import BaseModel

    from app.application.commands.base import BaseCommand
    from app.application.dispatching.context import CommandContext
    from app.application.dispatching.registry import CommandHandlerRegistry
    from app.application.exceptions.idempotency import IdempotencyUnavailableError
    from app.application.idempotency.policy import IdempotencyPolicy
    from app.infrastructure.di.command_bus import build_postgres_command_bus

    class Reply(BaseModel):
        number: int

    class Command(BaseCommand[Reply]):
        value: str

    class OfflineHotStore:
        async def claim(self, *args):
            raise IdempotencyUnavailableError("Redis offline")

    barrier = asyncio.Barrier(2)
    handler_sessions = []

    def handler_factory(session):
        async def handler(command):
            number = len(handler_sessions) + 1
            handler_sessions.append(session)
            await session.execute(
                text("INSERT INTO effects VALUES (:id, :value)"),
                {"id": number, "value": command.value},
            )
            await barrier.wait()
            return Reply(number=number)

        return handler

    registry = CommandHandlerRegistry()
    registry.register(
        Command,
        handler_factory,
        result_type=Reply,
        operation="test.commit.v1",
        idempotency_policy=IdempotencyPolicy(),
    )
    bus = build_postgres_command_bus(
        registry,
        sessions=sessions,
        dependencies_factory=lambda session: session,
        hot_store=OfflineHotStore(),
    )
    ctx = CommandContext(idempotency_key="same", idempotency_scope="user:1")
    async with asyncio.timeout(15):
        first, second = await asyncio.gather(
            bus.dispatch(Command(value="same"), ctx),
            bus.dispatch(Command(value="same"), ctx),
        )
    assert first == second
    assert handler_sessions[0] is not handler_sessions[1]
    async with sessions() as session:
        assert (
            await session.execute(text("SELECT id FROM effects"))
        ).scalars().all() == [first.number]
    replay = await bus.dispatch(Command(value="same"), ctx)
    assert replay == first
    assert len(handler_sessions) == 2


async def test_completion_constraint_migration_preserves_snapshot_and_allows_marker(
    sessions,
):
    from pathlib import Path

    from sqlalchemy.exc import IntegrityError

    migration = (
        Path(__file__).resolve().parents[2]
        / "src/app/infrastructure/idempotency/postgres/migrations/001_allow_completion_marker.sql"
    ).read_text(encoding="utf-8")
    marker_identity = identity().model_copy(update={"key_digest": b"m" * 32})
    marker = CompletedIdempotencyResult(
        result_type="completion",
        request_fingerprint=b"f" * 32,
        expires_at=utc_now() + timedelta(seconds=3600),
    )
    async with sessions() as session:
        store = PostgresDurableIdempotencyStore(session)
        async with session.begin():
            # Recreate the previous installed constraint before applying the migration.
            await session.execute(
                text(
                    "ALTER TABLE idempotency_records "
                    "DROP CONSTRAINT ck_idempotency_records_replayable_result, "
                    "ADD CONSTRAINT ck_idempotency_records_replayable_result CHECK "
                    "(result_payload IS NOT NULL OR (resource_type IS NOT NULL AND resource_id IS NOT NULL))"
                )
            )
            assert await store.try_add_completed(identity(), completed("existing"))
        async with session.begin():
            await session.execute(text(migration))
            assert await store.try_add_completed(marker_identity, marker)
        async with session.begin():
            assert (await store.get_completed(identity())).result_payload == {
                "value": "existing"
            }
            assert await store.get_completed(marker_identity) == marker
            assert not await store.try_add_completed(
                marker_identity, completed("must not replace")
            )

        with pytest.raises(IntegrityError):
            async with session.begin():
                await session.execute(
                    update(IdempotencyRecordORM)
                    .where(
                        IdempotencyRecordORM.key_digest == marker_identity.key_digest
                    )
                    .values(result_payload={"value": "must not store"})
                )
        async with session.begin():
            assert await store.get_completed(marker_identity) == marker

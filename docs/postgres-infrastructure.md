# PostgreSQL infrastructure

The domain aggregates and value objects are the source of truth. This schema follows the current code: settings own locale (`ru`/`en`), bio is at most 255 characters without newlines, and avatar references are nullable strings. Older handbook examples do not override these contracts.

## Available components

- `database/models`: profiles, user_settings and consumer-scoped processed_events.
- `database/metadata.py`: complete metadata including durable idempotency.
- `database/repositories.py`: detached aggregate reads, atomic insert-if-absent, unique username and conditional version updates.
- `database/readers.py`: read-only port surfaces.
- `database/inbox.py`: durable fence keyed by consumer and event ID; no replay TTL.
- `database/runtime.py`: process engine, per-scope sessions, read-only transactions, connection probe and disposal.
- `di/profiles.py`: registers all five existing commands using the same session for repositories, Inbox and durable execution.
- `application/idempotency/registration.py`: wraps default provisioning at the application boundary. If event_id is present, Inbox and profile/settings are committed by the command UoW together. If absent, lazy provisioning still uses insert-if-absent.

Repositories never commit. Use the bus for commands; do not place a second UoW around bus dispatch. For direct adapter use, enter SqlAlchemyUnitOfWork first. Runtime read scopes use PostgreSQL READ ONLY. Returned aggregates are detached values: unsaved mutation cannot leak into the database.

Profiles and settings deliberately have independent primary keys without a cross-table foreign key: the existing application contract supports repairing either missing half. Provisioning joins both operations in one transaction.

Update writes the version already advanced by the aggregate. It does not increment it again. The expected_version predicate selects the SQL winner; the returned value is hydrated from RETURNING. No-op handlers avoid writing. A stale command under a new idempotency key still raises its original version conflict; a duplicate losing OCC may replay only the committed record for its exact idempotency identity.

## Configuration

DatabaseSettings reads process environment explicitly. It does not automatically read a .env file. URLs are masked in settings representations.

| Variable | Default |
|---|---|
| PROFILE_DATABASE_URL | Required, postgresql+asyncpg URL |
| PROFILE_DATABASE_POOL_SIZE | 5 |
| PROFILE_DATABASE_MAX_OVERFLOW | 5 |
| PROFILE_DATABASE_POOL_TIMEOUT | 5 seconds |
| PROFILE_DATABASE_COMMAND_TIMEOUT | 10 seconds |

Choose database roles and secrets for the target environment. Test credentials below are only for disposable local containers.

## Migrations

From the service directory:

```powershell
$env:PROFILE_DATABASE_URL = 'postgresql+asyncpg://profile_test:profile_test@127.0.0.1:55432/profile_test'
poetry run alembic upgrade head
poetry run alembic check
```

The immutable baseline creates profiles, user_settings, processed_events and idempotency_records. It contains fixed operations rather than importing live model definitions. Run migrations once per deployment, before starting replicas. Downgrade is destructive and is tested only on isolated schemas.

The runtime image includes Alembic and the revisions:

```powershell
docker run --rm --env-file .env andruha/user-profile-service:local alembic upgrade head
```

The old standalone idempotency SQL file remains a regression fixture for previously implemented completion-marker behavior. It is not an extra installation step for the baseline.

## Composition

```python
database = ProfileDatabase(DatabaseSettings())
try:
    bus = build_profile_command_bus(
        database.sessions,
        hot_store=hot_store,
        mutation_policy=IdempotencyPolicy(),
    )
    await bus.dispatch(create_default_command)
    async with database.readers() as readers:
        profile = await GetMyProfileHandler(readers.profiles)(query)
finally:
    await database.close()
```

The composition root provides the Redis adapter and explicit mutation policy. Mutating commands with that policy require a trusted scope and idempotency key. The default provisioning command uses database uniqueness and, when event_id is supplied, the durable Inbox instead of time-limited HTTP replay.

HTTP and Kafka transports are not connected by this change. The current HTTP factory still exposes health endpoints only; its readiness does not call ProfileDatabase.check_ready yet. That probe checks database connectivity, not the installed migration revision. The next transport/bootstrap stage must own resource lifecycle, supply configuration and wire appropriate readiness.

Avatar object ownership/READY validation remains a separate Object Storage adapter. No external call is added inside the database transaction.

## Real integration tests

Create disposable infrastructure using unused localhost ports:

```powershell
docker run --detach --rm --name profile-test-postgres -e POSTGRES_USER=profile_test -e POSTGRES_PASSWORD=profile_test -e POSTGRES_DB=profile_test -p 127.0.0.1:55432:5432 postgres:17.10-bookworm
docker run --detach --rm --name profile-test-valkey -p 127.0.0.1:56379:6379 valkey/valkey:8.1.9-alpine3.24

$env:TEST_PROFILE_POSTGRES_DSN = 'postgresql+asyncpg://profile_test:profile_test@127.0.0.1:55432/profile_test'
$env:TEST_IDEMPOTENCY_POSTGRES_DSN = $env:TEST_PROFILE_POSTGRES_DSN
$env:TEST_IDEMPOTENCY_REDIS_URL = 'redis://127.0.0.1:56379/0'
$env:REQUIRE_INFRASTRUCTURE_TESTS = '1'
poetry run pytest tests/integration/test_profile_persistence.py tests/integration/test_idempotency_postgres.py tests/integration/test_idempotency_redis.py

docker stop profile-test-postgres profile-test-valkey
```

Wait for PostgreSQL readiness before running tests. Each PostgreSQL test creates, migrates and drops only its own randomly named schema; Redis tests use a unique namespace. Do not point these variables at production.

Coverage includes concurrent provisioning, missing-half repair, SQL OCC, username races, read-only scopes, schema roundtrip, invalid privacy constraints, atomic Inbox and pair creation, all command registrations, no-op, rollback of business effects when replay persistence fails and PostgreSQL replay without Redis.

CI provisions PostgreSQL/Valkey, sets required test URLs, and runs unit, handler and integration suites. Missing URLs fail when REQUIRE_INFRASTRUCTURE_TESTS is set. Existing business HTTP tests intentionally remain red until the transport stage is implemented; they are not skipped or weakened here.

# Andruha User Profile Service

## Purpose and current status

The service contains the profile/settings domain, eleven application handlers, transactional command dispatch, and PostgreSQL repositories, readers, durable idempotency and migrations. Profile/settings HTTP reads and conditional writes, username search, local JWT verification are connected. Reads never create missing data. The Kafka consumer is not connected yet. See [PostgreSQL infrastructure](docs/postgres-infrastructure.md) for configuration and real integration tests.

## Responsibility and explicit non-responsibilities

Own editable public profile data and user preferences/privacy settings.

It does not own credentials, authentication sessions, messages, media object bytes, or realtime delivery.

## Hexagonal/DDD layer map

- `domain`: aggregates, value objects and privacy invariants; independent of transports and storage.
- `application`: command/query handlers, dispatch, idempotency and owned ports; depends on domain.
- `infrastructure`: PostgreSQL/Redis adapters and dependency factories implementing application ports.
- `entrypoints`: transport translation through Dishka, application queries and transactional command dispatch.
- `core`: configuration and cross-cutting logging only.

The dependency direction is `entrypoints -> application -> domain` and `infrastructure -> application ports -> domain`.

## Entrypoints

- `app.entrypoints.http.main:create_app` - FastAPI factory
- `GET /health/live` - process liveness
- `GET /health/ready` - initialized application readiness

- `GET /api/v1/profiles/me` - own profile, using the verified JWT `sub`
- `GET /api/v1/profiles/{user_id}` - public profile with privacy rules
- `POST /api/v1/profiles/batch` - ordered batch of public profiles
- `PATCH /api/v1/profiles/me` - conditional profile update
- `GET /api/v1/settings/me`, `PATCH /api/v1/settings/me` - own settings
- `GET /api/v1/profiles?username=...` - exact username search
- `HEAD /internal/v1/profiles/{user_id}` - internal existence check

See [HTTP API](src/app/entrypoints/http/README.md) for authentication configuration,
request/response contracts, and verification commands.

## Configuration variables

- `SERVICE_NAME`, `APP_VERSION`, `APP_ENVIRONMENT`
- `HOST`, `PORT`
- `DEV_LOGS`, `LOG_LEVEL`, `MUTE_LOGGERS`

## Liveness and readiness

`GET /health/live` reports that the process is running. `GET /health/ready` reports readiness after application lifespan initialization. It intentionally performs no fake dependency probes.

## Local build and run status

Runtime and test dependencies are declared and locked for Python 3.14. The
service can be verified from this repository with:

```powershell
poetry sync --with dev --no-root
poetry run ruff check .
poetry run ruff format --check .
poetry run ty check --error-on-warning
poetry run pytest
docker build --target runtime --tag andruha/user-profile-service:local .
```

`.github/workflows/ci.yml` runs lint, ty type checking, unit, handler and integration
tests, branch coverage >= 80%, runtime dependency audit, secret scanning, and a
Docker smoke test. `.github/workflows/release.yml` publishes a verified image
to GHCR only for a version tag. HTTP acceptance tests cover reads, writes and recovery with signed tokens; live HTTP tests also use PostgreSQL/Valkey when configured. PostgreSQL/Redis adapter tests require the environment described in the infrastructure guide.

## Canonical project material

- [Documentation](https://github.com/yemeal/andruha-messenger/tree/main/docs)
- [Contracts](https://github.com/yemeal/andruha-messenger/tree/main/contracts)

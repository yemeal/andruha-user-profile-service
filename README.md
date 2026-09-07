# Andruha User Profile Service

## Purpose and current status

The service contains the profile/settings domain, eleven application handlers, transactional command dispatch, and PostgreSQL repositories, readers, durable idempotency and migrations. Business HTTP routes and the Kafka consumer are not connected yet. See [PostgreSQL infrastructure](docs/postgres-infrastructure.md) for configuration and real integration tests.

## Responsibility and explicit non-responsibilities

Own editable public profile data and user preferences/privacy settings.

It does not own credentials, authentication sessions, messages, media object bytes, or realtime delivery.

## Hexagonal/DDD layer map

- `domain`: aggregates, value objects and privacy invariants; independent of transports and storage.
- `application`: command/query handlers, dispatch, idempotency and owned ports; depends on domain.
- `infrastructure`: PostgreSQL/Redis adapters and dependency factories implementing application ports.
- `entrypoints`: transport translation that will call application services.
- `core`: configuration and cross-cutting logging only.

The dependency direction is `entrypoints -> application -> domain` and `infrastructure -> application ports -> domain`.

## Entrypoints

- `app.entrypoints.http.main:create_app` - FastAPI factory
- `GET /health/live` - process liveness
- `GET /health/ready` - initialized application readiness

No business API or transport contract is available yet.

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
poetry run pytest
docker build --target runtime --tag andruha/user-profile-service:local .
```

`.github/workflows/ci.yml` runs lint, strict Pyright, unit, handler and integration
tests, branch coverage >= 80%, runtime dependency audit, secret scanning, and a
Docker smoke test. `.github/workflows/release.yml` publishes a verified image
to GHCR only for a version tag. Business APIs remain deferred; their existing acceptance tests are intentionally red. PostgreSQL/Redis adapter tests require the environment described in the infrastructure guide.

## Canonical project material

- [Documentation](https://github.com/yemeal/andruha-messenger/tree/main/docs)
- [Contracts](https://github.com/yemeal/andruha-messenger/tree/main/contracts)

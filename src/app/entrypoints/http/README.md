# Profile and settings HTTP API

The factory is `app.entrypoints.http.main:create_app`. HTTP routes construct
application queries/commands and use Dishka providers. JWTSettings lives in
core/settings/jwt.py and is exposed by SettingsProvider; HTTPProvider constructs
the verifier. The application factory accepts a Dishka container for overrides,
not a separate settings/verifier instance. Privacy, ordering and persistence
stay in their existing layers.

## Authentication

Configure `JWT_PUBLIC_KEYS` with a JSON object mapping trusted Identity `kid` values
to mounted RSA PEM **public** key files, for example:

```dotenv
JWT_PUBLIC_KEYS={"identity-v1":"/run/configs/identity_jwt_public_key"}
JWT_ISSUER=andruha-identity-service
JWT_AUDIENCE=andruha-user-profile-service
JWT_CLOCK_SKEW_SECONDS=30
```

Identity must include `andruha-user-profile-service` in its issued `aud` claim.
Send `Authorization: Bearer <access-token>`. Cookie-to-Bearer mapping belongs to
the gateway. Client identity headers, query parameters and body fields never
supply the authenticated viewer.

The verifier follows Identity's local key-ring pattern: fixed RS256, `typ=at+jwt`,
trusted `kid`, signature, issuer, own audience, required `iat`/`exp`, UUID `sub` and
`jti`, and known `USER`/`ADMIN` role. Keys must be RSA >= 2048 bits and are loaded
once per application instance. Multiple configured kids support key rotation;
restart the application after changing the ring. Keys/URLs from token headers
are never loaded. Claim validation uses [PyJWT](https://pyjwt.readthedocs.io/en/stable/api.html).

An empty key ring leaves anonymous public reads and health routes available;
authenticated requests return `503` until keys are configured. A configured file
that is missing, malformed, private, non-RSA or too small fails application startup.
Readiness retains its existing process-initialization meaning; it does not probe
PostgreSQL or assert that JWT has been configured.

## Routes

| Route | Authentication | Response |
| --- | --- | --- |
| `GET /api/v1/profiles/me` | Required | `ProfileDTO`, `ETag: "<version>"`, `Cache-Control: private, no-cache` |
| `GET /api/v1/profiles/{user_id}` | Optional | `PublicProfileDTO`, `Cache-Control: no-store` |
| `POST /api/v1/profiles/batch` | Optional | Array of `PublicProfileDTO`, `Cache-Control: no-store` |

All GET routes and HEAD are pure reads. A missing owner profile or settings returns
404; reading never creates default rows. Identity provisions both rows synchronously
before completing registration.

Additional routes:

| Route | Contract |
| --- | --- |
| `PATCH /api/v1/profiles/me` | JWT required; profile update |
| `GET /api/v1/settings/me` | JWT required; SettingsDTO with ETag and private cache |
| `PATCH /api/v1/settings/me` | JWT required; settings update |
| `GET /api/v1/profiles?username=...` | Optional JWT; exact, case-insensitive search with privacy |
| `HEAD /internal/v1/profiles/{user_id}` | 200/404, empty body, no-store |
| `PUT /internal/v1/profiles/{user_id}` | Identity service token; creates default profile and settings; 204 |

The internal path must not be published by the gateway. PUT requires `X-Service-Token`
matching `INTERNAL_API_TOKEN`; configure the same secret as Identity's
`PROFILE_SERVICE_TOKEN`. `InternalAPISettings` lives in core/settings and is supplied
through Dishka. Missing token configuration returns 503; absent or invalid credentials
return 401. HEAD retains its existing private-network contract.

PUT accepts only `{"registered_at":"2026-01-01T00:00:00Z"}` with a timezone-aware
registration timestamp. It dispatches `CreateDefaultProfileCommand` through the
existing CommandBus with COMPLETION_ONLY. Profile and settings creation is atomic;
INSERT ON CONFLICT preserves existing rows and their versions. The trusted
idempotency scope is `identity:profile-provisioning`, with the user UUID as key.
Retries must retain both UUID and timestamp. An identical completed call returns
204; conflicting payload or in-flight duplicate returns 409 (the latter includes
Retry-After). Identity may retry transient failures with the original payload.

This is initialization, not data recovery: retained completion markers intentionally
do not recreate manually deleted rows. Historical missing profiles require a separate
operational reconciliation before enforcing the registration invariant. The call
does not make Identity and Profile databases a single atomic transaction.

## Conditional writes

Both PATCH routes require `If-Match: "<version>"` and `Idempotency-Key` (1..255
characters). Missing If-Match returns 428; malformed, weak, wildcard, list or
nonpositive version ETags return 400. A missing/invalid idempotency key returns
422. A stale version returns 409 and includes parameters.current_version when
known. No update occurs on a conflict. Success returns the resulting DTO and
ETag with Cache-Control: private, no-cache; unchanged values retain the version.

Idempotency scope comes only from the verified JWT subject. Identical retries
with the same key replay the committed response; a different payload/version
with that key returns 409. Processing uses the existing durable mechanism and
per-dispatch transaction, including when the hot store is unavailable. An
in-flight duplicate returns 409 with Retry-After; unavailable durable execution
returns 503. A missing profile or settings on PATCH returns 404.

Profile body fields: display_name, bio, username. Omitted fields stay unchanged;
bio null or an empty string clears the biography. Explicit null for other fields,
unknown fields and empty patches return 422. Username collisions return 409.

Settings body fields: theme, locale, timezone, privacy. Privacy is a partial
object containing who_can_see_avatar, who_can_find_by_username and/or
who_can_see_bio; omitted values are preserved. Empty privacy objects, null and
unknown fields are rejected. Domain values and invariants remain authoritative.

```http
PATCH /api/v1/settings/me
Authorization: Bearer <access-token>
If-Match: "1"
Idempotency-Key: <unique-client-operation-id>
Content-Type: application/json

{"theme":"dark","privacy":{"who_can_see_bio":"NOBODY"}}
```

The owner response uses the current application DTO: `user_id`, `username`,
`display_name`, `bio`, `avatar_key`, `status`, `is_verified`, `version`,
`created_at`, `updated_at`. Public responses expose only `user_id`, `username`,
`display_name`, `bio`, `avatar_key`, `is_verified`. The existing application privacy
policy masks bio/avatar for other viewers and grants the owner access. Public
responses do not expose account status, credentials, or settings.

Batch request:

```json
{"user_ids": ["0194d000-0000-7000-8000-000000000001", "0194d000-0000-7000-8000-000000000002"]}
```

The body allows only `user_ids`, with 1..100 UUID entries, matching the application
query's limit. Duplicate IDs are removed in first-occurrence order. Missing
profiles are omitted; if all are missing the result is `[]`. The response follows
requested order, independent of storage order. Batch reads use the existing
profile/settings batch readers, with no per-profile queries.

Missing/invalid required credentials return `401` with `WWW-Authenticate: Bearer`.
An invalid supplied token is also rejected on optional-auth routes; it does not
silently become an anonymous request. A missing profile returns `404`, invalid
UUID/body returns `422`, and unavailable privacy settings return `503` without
exposing profile details. Unexpected failures use the existing safe error
middleware. Responses retain `X-Request-Id`.

## Checks

```powershell
poetry run pytest tests/unit/test_http_security.py tests/integration/test_profile_reads.py tests/integration/test_profile_endpoints.py tests/integration/test_settings_endpoints.py tests/integration/test_internal_provisioning.py tests/integration/test_http_bootstrap.py
poetry run ruff check .
poetry run ruff format --check .
```

HTTP acceptance tests exercise real signed tokens, application handlers, and
Dishka with isolated in-memory readers. Existing PostgreSQL/Valkey integration
tests separately validate the persistence adapters. The HTTP write tests use the production command bus and storage-port fakes.
`test_profile_http_postgres.py` exercises the default DI providers, concurrent
provisioning/OCC, durable replay, rollback and late registration with actual services.
It uses TEST_PROFILE_POSTGRES_DSN and TEST_IDEMPOTENCY_REDIS_URL, with isolated
schemas and key namespaces.

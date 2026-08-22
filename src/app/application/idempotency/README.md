# Idempotency Subsystem Architecture

## Overview

This module provides transport-neutral, distributed idempotency orchestration for the application layer.

```
Entrypoint
    ↓ (Command + CommandContext)
CommandBus
    ↓ (transparent interception)
IdempotencyMiddleware (Single Public Integration Point)
    ↓
IdempotencyCoordinator (Internal State Machine Orchestrator)
    ├── Hot Storage (Redis/Valkey: Distributed Leases & Fast Replay Cache)
    └── Transactional Execution (PostgreSQL: Atomic Business UoW + Durable Replay Fence)
         ↓
      Handler (Business Logic - Agnostic of Idempotency)
```

---

## Key Guarantees and Execution Modes

### 1. `HOT_ONLY` Mode
- **Design Intent**: Maximum throughput and low latency when durable persistence is not required.
- **Fail Semantics**: **Fail-closed**. If the hot store (Redis) is unavailable, the coordinator raises `IdempotencyUnavailableError` rather than silently skipping idempotency protections.
- **Lifecycle**: `claim` lease → execute handler → `complete` cache entry (or `release` on failure).

### 2. `HOT_DURABLE` Mode
- **Design Intent**: Zero dual-write hazard. Guaranteed atomic execution of business state mutations and durable idempotency records within a single database transaction (Unit of Work).
- **Fail Semantics**: **Graceful degradation**. If the hot store is unavailable, the coordinator falls back to `TransactionalIdempotencyExecution` directly against the durable store.
- **Lifecycle**: `claim` lease → heartbeat renew → transactional DB execution + commit → `complete` hot cache.

---

## Terminology Mapping

| Concept | Description |
|---|---|
| `IdempotencyKey` | Scoped operation key: `(subject_id, operation, key_digest)` |
| `key_digest` | 32-byte SHA-256 digest of client raw `Idempotency-Key` |
| `request_fingerprint` | Canonicalized SHA-256 digest of command/request payload |
| `ClaimStatus` | `ACQUIRED`, `REPLAY`, `CONFLICT`, `IN_PROGRESS` |
| `lease_token` | UUIDv7 token identifying the current lease owner |
| `IdempotencyMiddleware` | The single public integration point for the CommandBus |
| `IdempotencyPolicy` | Configuration defining execution mode (`HOT_ONLY` vs `HOT_DURABLE`) and lease duration |

---

## Application Exceptions

- `IdempotencyConflictError`: The same idempotency key was reused with a different request fingerprint.
- `IdempotencyInProgressError`: A concurrent operation for this key is currently executing.
- `IdempotencyUnavailableError`: Storage is unavailable in fail-closed mode (`HOT_ONLY`).
- `StoredReplayUnavailableError`: Stored payload envelope could not be decrypted or deserialized.

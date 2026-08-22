from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import NoReturn, cast
from uuid import UUID

import redis.exceptions
import structlog
from pydantic import TypeAdapter
from redis.asyncio import Redis

from app.application.exceptions.idempotency import (
    IdempotencyUnavailableError,
)
from app.application.idempotency.models import (
    ClaimResult,
    ClaimStatus,
    CompletedIdempotencyResult,
    IdempotencyKey,
)

logger = structlog.get_logger()
_JSON_ADAPTER = TypeAdapter(dict[str, object])


class RedisHotIdempotencyStore:
    """Адаптер горячего хранилища блокировок и кэша на Redis/Valkey с атомарными Lua-скриптами CAS."""

    _CLAIM_SCRIPT = """
local state = redis.call('HGET', KEYS[1], 'state')
if not state then
    if redis.call('EXISTS', KEYS[1]) == 1 then
        return {5}
    end
    redis.call(
        'HSET',
        KEYS[1],
        'format_version', '1',
        'state', 'processing',
        'request_fingerprint', ARGV[1],
        'lease_token', ARGV[2]
    )
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
    return {1}
end
local format_version = redis.call('HGET', KEYS[1], 'format_version')
local current_fingerprint = redis.call('HGET', KEYS[1], 'request_fingerprint')
local lease_owner = redis.call('HGET', KEYS[1], 'lease_token')
local result = redis.call('HGET', KEYS[1], 'result')
if format_version ~= '1' or not current_fingerprint then
    return {5}
end
if state == 'processing' and (not lease_owner or result) then
    return {5}
end
if state == 'completed' and (not result or lease_owner) then
    return {5}
end
if current_fingerprint ~= ARGV[1] then
    return {3}
end
if state == 'completed' then
    return {2, result}
end
if state == 'processing' then
    return {4}
end
return {5}
"""

    _RENEW_SCRIPT = """
local format_version = redis.call('HGET', KEYS[1], 'format_version')
local state = redis.call('HGET', KEYS[1], 'state')
local lease_owner = redis.call('HGET', KEYS[1], 'lease_token')
local request_fingerprint = redis.call('HGET', KEYS[1], 'request_fingerprint')
if format_version == '1' and state == 'processing'
    and lease_owner == ARGV[1] and request_fingerprint then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
    return 1
end
return 0
"""

    _COMPLETE_SCRIPT = """
local format_version = redis.call('HGET', KEYS[1], 'format_version')
local state = redis.call('HGET', KEYS[1], 'state')
local lease_owner = redis.call('HGET', KEYS[1], 'lease_token')
local request_fingerprint = redis.call('HGET', KEYS[1], 'request_fingerprint')
if format_version == '1' and state == 'processing'
    and lease_owner == ARGV[1] and request_fingerprint == ARGV[4] then
    redis.call(
        'HSET',
        KEYS[1],
        'state', 'completed',
        'result', ARGV[2]
    )
    redis.call('HDEL', KEYS[1], 'lease_token')
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
    return 1
end
return 0
"""

    _RELEASE_SCRIPT = """
local format_version = redis.call('HGET', KEYS[1], 'format_version')
local state = redis.call('HGET', KEYS[1], 'state')
local lease_owner = redis.call('HGET', KEYS[1], 'lease_token')
if format_version == '1' and state == 'processing' and lease_owner == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""

    def __init__(
        self,
        redis_client: Redis,
        *,
        result_ttl_seconds: int,
        key_namespace: str = "andruha-user-profile-service:idempotency:v1",
    ) -> None:
        if result_ttl_seconds <= 0:
            raise ValueError("result_ttl_seconds must be positive")
        if not key_namespace:
            raise ValueError("key_namespace must not be empty")
        self._redis = redis_client
        self._result_ttl_seconds = result_ttl_seconds
        self._key_namespace = key_namespace

    async def claim(
        self,
        identity: IdempotencyKey,
        request_fingerprint: bytes,
        lease_token: UUID,
        lease_seconds: int,
    ) -> ClaimResult:
        if len(request_fingerprint) != 32:
            raise ValueError(
                "request_fingerprint must be a full 32-byte SHA-256 digest"
            )
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        raw: object
        try:
            raw = cast(
                object,
                await self._redis.eval(
                    self._CLAIM_SCRIPT,
                    1,
                    self._storage_key(identity),
                    request_fingerprint.hex(),
                    str(lease_token),
                    str(lease_seconds),
                ),
            )
        except redis.exceptions.RedisError as error:
            self._raise_unavailable("claim", error)

        try:
            code = self._result_code(raw)
            if not isinstance(raw, (list, tuple)):
                raise RuntimeError(
                    "Redis idempotency script returned malformed result structure"
                )
            values = cast(Sequence[object], raw)
            if code == 1:
                return ClaimResult(status=ClaimStatus.ACQUIRED)
            if code == 2:
                if len(values) < 2 or values[1] is None:
                    raise RuntimeError("completed entry has no result payload")
                completed = self._decode_completed(values[1])
                if completed.request_fingerprint != request_fingerprint:
                    raise RuntimeError(
                        "completed result fingerprint does not match entry"
                    )
                return ClaimResult(
                    status=ClaimStatus.REPLAY,
                    completed=completed,
                )
            if code == 3:
                return ClaimResult(status=ClaimStatus.CONFLICT)
            if code == 4:
                return ClaimResult(status=ClaimStatus.IN_PROGRESS)
            raise RuntimeError(f"idempotency entry has unknown state code {code}")
        except RuntimeError as error:
            self._raise_corrupted(error)

    async def renew(
        self,
        identity: IdempotencyKey,
        lease_token: UUID,
        lease_seconds: int,
    ) -> bool:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        try:
            result = await self._redis.eval(
                self._RENEW_SCRIPT,
                1,
                self._storage_key(identity),
                str(lease_token),
                str(lease_seconds),
            )
            return bool(result)
        except redis.exceptions.RedisError as error:
            self._raise_unavailable("renew", error)

    async def complete(
        self,
        identity: IdempotencyKey,
        lease_token: UUID,
        result: CompletedIdempotencyResult,
    ) -> bool:
        encoded = self._encode_completed(result)
        try:
            completed = await self._redis.eval(
                self._COMPLETE_SCRIPT,
                1,
                self._storage_key(identity),
                str(lease_token),
                encoded,
                str(self._result_ttl_seconds),
                result.request_fingerprint.hex(),
            )
            return bool(completed)
        except redis.exceptions.RedisError as error:
            self._raise_unavailable("complete", error)

    async def release(
        self,
        identity: IdempotencyKey,
        lease_token: UUID,
    ) -> bool:
        try:
            released = await self._redis.eval(
                self._RELEASE_SCRIPT,
                1,
                self._storage_key(identity),
                str(lease_token),
            )
            return bool(released)
        except redis.exceptions.RedisError as error:
            self._raise_unavailable("release", error)

    def _storage_key(self, identity: IdempotencyKey) -> str:
        material = (
            identity.subject_id.encode("utf-8")
            + b"\0"
            + identity.operation.encode("utf-8")
            + b"\0"
            + identity.key_digest
        )
        digest = hashlib.sha256(material).hexdigest()
        return f"{self._key_namespace}:{digest}"

    @staticmethod
    def _result_code(raw: object) -> int:
        if not isinstance(raw, (list, tuple)) or not raw:
            raise RuntimeError("Redis idempotency script returned malformed result")
        values = cast(Sequence[object], raw)
        value = values[0]
        if not isinstance(value, (str, bytes, int)):
            raise RuntimeError("Redis idempotency script returned malformed result")
        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise RuntimeError(
                "Redis idempotency script returned malformed result"
            ) from error

    @staticmethod
    def _encode_completed(result: CompletedIdempotencyResult) -> str:
        payload = cast(
            dict[str, object],
            result.model_dump(mode="json", exclude={"request_fingerprint"}),
        )
        payload["request_fingerprint"] = result.request_fingerprint.hex()
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @staticmethod
    def _decode_completed(raw: object) -> CompletedIdempotencyResult:
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            if not isinstance(raw, str):
                raise TypeError("completed result is not JSON text")
            payload = _JSON_ADAPTER.validate_json(raw)
            request_fingerprint = payload.get("request_fingerprint")
            if not isinstance(request_fingerprint, str):
                raise TypeError("completed result request fingerprint is not text")
            payload["request_fingerprint"] = bytes.fromhex(request_fingerprint)
            return CompletedIdempotencyResult.model_validate(payload)
        except (KeyError, TypeError, UnicodeError, ValueError) as error:
            raise RuntimeError("Redis completed result is malformed") from error

    @staticmethod
    def _raise_unavailable(operation: str, error: Exception) -> NoReturn:
        logger.warning(
            "idempotency_redis_unavailable",
            operation=operation,
            error_type=type(error).__name__,
        )
        raise IdempotencyUnavailableError() from error

    @staticmethod
    def _raise_corrupted(error: Exception) -> NoReturn:
        logger.error(
            "idempotency_redis_corrupted",
            error_type=type(error).__name__,
        )
        raise IdempotencyUnavailableError() from error

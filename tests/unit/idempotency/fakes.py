"""Test adapters with real per-dispatch state, rollback and expiry semantics."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.application.exceptions.idempotency import IdempotencyUnavailableError
from app.application.idempotency.models import ClaimResult, ClaimStatus


@dataclass
class Clock:
    value: datetime = field(default_factory=lambda: datetime(2026, 9, 4, tzinfo=UTC))

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)


@dataclass
class State:
    clock: Clock = field(default_factory=Clock)
    effects: list = field(default_factory=list)
    records: dict = field(default_factory=dict)
    hot: dict = field(default_factory=dict)
    sessions: list = field(default_factory=list)
    hot_unavailable: bool = False


class Session:
    def __init__(self, state):
        self.state = state
        self.effects = []
        self.records = {}
        self.active = False
        self.closed = False
        state.sessions.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    def stage(self, effect):
        assert self.active
        self.effects.append(effect)


class Uow:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        assert not self.session.active
        self.session.active = True
        return self

    async def __aexit__(self, exc_type, *_):
        if exc_type is None:
            self.session.state.effects.extend(self.session.effects)
            self.session.state.records.update(self.session.records)
        self.session.effects.clear()
        self.session.records.clear()
        self.session.active = False


class DurableStore:
    def __init__(self, session, *, clock):
        self.session = session
        self.clock = clock

    async def get_completed(self, identity):
        assert self.session.active
        found = self.session.state.records.get(identity)
        return found if found is not None and found.expires_at > self.clock() else None

    async def try_add_completed(self, identity, completed):
        assert self.session.active
        if await self.get_completed(identity) is not None:
            return False
        self.session.records[identity] = completed
        return True


class HotStore:
    def __init__(self, state):
        self.state = state

    async def claim(self, identity, fingerprint, owner, lease_seconds):
        if self.state.hot_unavailable:
            raise IdempotencyUnavailableError("hot offline")
        entry = self.state.hot.get(identity)
        if entry and entry["expires"] <= self.state.clock():
            del self.state.hot[identity]
            entry = None
        if entry is None:
            self.state.hot[identity] = {
                "fingerprint": fingerprint,
                "owner": owner,
                "expires": self.state.clock() + timedelta(seconds=lease_seconds),
            }
            return ClaimResult(status=ClaimStatus.ACQUIRED)
        if entry["fingerprint"] != fingerprint:
            return ClaimResult(status=ClaimStatus.CONFLICT)
        if "result" in entry:
            return ClaimResult(status=ClaimStatus.REPLAY, completed=entry["result"])
        return ClaimResult(status=ClaimStatus.IN_PROGRESS)

    async def renew(self, identity, owner, lease_seconds):
        entry = self.state.hot.get(identity)
        if (
            not entry
            or entry.get("owner") != owner
            or entry["expires"] <= self.state.clock()
        ):
            return False
        entry["expires"] = self.state.clock() + timedelta(seconds=lease_seconds)
        return True

    async def complete(self, identity, owner, result, *, cache_ttl_seconds):
        entry = self.state.hot.get(identity)
        if (
            not entry
            or entry.get("owner") != owner
            or entry["expires"] <= self.state.clock()
        ):
            return False
        deadline = min(
            result.expires_at, self.state.clock() + timedelta(seconds=cache_ttl_seconds)
        )
        if deadline <= self.state.clock():
            del self.state.hot[identity]
            return False
        self.state.hot[identity] = {
            "fingerprint": result.request_fingerprint,
            "result": result,
            "expires": deadline,
        }
        return True

    async def release(self, identity, owner):
        entry = self.state.hot.get(identity)
        if entry and entry.get("owner") == owner:
            del self.state.hot[identity]
            return True
        return False


def build_bus(monkeypatch, registry, state):
    # Exercise the production scope builder; replace only persistence adapters.
    import app.infrastructure.di.command_bus as assembly

    monkeypatch.setattr(assembly, "SqlAlchemyUnitOfWork", Uow)
    monkeypatch.setattr(assembly, "PostgresDurableIdempotencyStore", DurableStore)
    return assembly.build_postgres_command_bus(
        registry,
        sessions=lambda: Session(state),
        dependencies_factory=lambda session: session,
        hot_store=HotStore(state),
        clock=state.clock,
    )

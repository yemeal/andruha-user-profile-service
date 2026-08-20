"""Юнит-тесты для базовых классов домена (Entity, MutableEntity, VersionedMutableEntity)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.base import (
    Entity,
    MutableEntity,
    VersionedMutableEntity,
)
from app.domain.exceptions import InvalidTimestampError, InvalidVersionError


class DummyEntity(Entity):
    name: str


class DummyMutableEntity(MutableEntity):
    name: str


class DummyVersionedEntity(VersionedMutableEntity):
    name: str


def test_entity_has_id_and_created_at() -> None:
    entity = DummyEntity(name="item1")
    assert isinstance(entity.id, uuid.UUID)
    assert isinstance(entity.created_at, datetime)
    assert entity.name == "item1"


def test_mutable_entity_has_no_version_by_default() -> None:
    mutable = DummyMutableEntity(name="item1")
    assert isinstance(mutable.id, uuid.UUID)
    assert isinstance(mutable.created_at, datetime)
    assert mutable.updated_at is None
    assert not hasattr(mutable, "version")


def test_mutable_entity_validates_timestamp_order() -> None:
    t0 = datetime.now(UTC)
    t_before = t0 - timedelta(seconds=10)

    with pytest.raises(InvalidTimestampError):
        DummyMutableEntity(
            name="item1",
            created_at=t0,
            updated_at=t_before,
        )


def test_mutable_entity_mark_updated() -> None:
    t0 = datetime.now(UTC)
    mutable = DummyMutableEntity(name="item1", created_at=t0)
    assert mutable.updated_at is None

    t1 = t0 + timedelta(minutes=1)
    mutable.mark_updated(now=t1)
    assert mutable.updated_at == t1
    assert not hasattr(mutable, "version")


def test_versioned_mutable_entity_has_version_and_validates_it() -> None:
    versioned = DummyVersionedEntity(name="versioned1")
    assert isinstance(versioned, VersionedMutableEntity)
    assert isinstance(versioned, MutableEntity)
    assert isinstance(versioned, Entity)
    assert versioned.version == 1
    assert versioned.updated_at is None

    # Невалидные версии вызывают InvalidVersionError
    with pytest.raises(InvalidVersionError):
        DummyVersionedEntity(name="versioned1", version=0)

    with pytest.raises(InvalidVersionError):
        DummyVersionedEntity(name="versioned1", version=-5)


def test_versioned_mutable_entity_increment_version() -> None:
    versioned = DummyVersionedEntity(name="versioned1")
    assert versioned.version == 1

    versioned.increment_version()
    assert versioned.version == 2

    versioned.increment_version()
    assert versioned.version == 3


def test_versioned_mutable_entity_mark_updated() -> None:
    t0 = datetime.now(UTC)
    versioned = DummyVersionedEntity(name="versioned1", created_at=t0)
    assert versioned.updated_at is None
    assert versioned.version == 1

    t1 = t0 + timedelta(minutes=1)
    versioned.mark_updated(now=t1)
    assert versioned.updated_at == t1
    assert versioned.version == 2

    t2 = t1 + timedelta(minutes=1)
    versioned.mark_updated(now=t2)
    assert versioned.updated_at == t2
    assert versioned.version == 3

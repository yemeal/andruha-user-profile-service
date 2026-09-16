"""Trusted registration provisioning through HTTP and durable command dispatch."""

from datetime import UTC, datetime

import pytest
from tests.integration.http_support import client as client
from tests.integration.http_support import harness as harness
from tests.integration.http_support import profile_client
from tests.integration.http_support import tokens as tokens

pytestmark = pytest.mark.integration
HEADERS = {"X-Service-Token": "test-service-token"}
BODY = {"registered_at": "2026-01-01T00:00:00Z"}


def test_provision_creates_both_rows_and_replays_without_reset(client, harness, tokens):
    url = f"/internal/v1/profiles/{harness.user_id}"
    created = client.put(url, headers=HEADERS, json=BODY)
    assert created.status_code == 204 and created.content == b""
    assert created.headers["cache-control"] == "no-store"
    assert harness.profiles._rows[harness.user_id].created_at == datetime(
        2026, 1, 1, tzinfo=UTC
    )
    assert harness.user_id in harness.settings._rows
    changed = client.patch(
        "/api/v1/profiles/me",
        headers=tokens.mutation(harness.user_id),
        json={"display_name": "Keep Name"},
    )
    assert changed.status_code == 200
    assert client.put(url, headers=HEADERS, json=BODY).status_code == 204
    assert harness.profiles._rows[harness.user_id].display_name == "Keep Name"
    assert harness.profiles._rows[harness.user_id].version == 2
    conflict = client.put(
        url, headers=HEADERS, json={"registered_at": "2025-01-01T00:00:00Z"}
    )
    assert conflict.status_code == 409


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-Service-Token": "wrong"}, {"Authorization": "Bearer test-service-token"}],
)
def test_provision_requires_service_credential(client, harness, headers):
    result = client.put(
        f"/internal/v1/profiles/{harness.user_id}", headers=headers, json=BODY
    )
    assert result.status_code == 401
    assert harness.profiles._rows == harness.settings._rows == {}


def test_provision_without_config_is_unavailable(harness, tokens):
    with profile_client(harness, tokens.settings, internal_token=None) as client:
        result = client.put(
            f"/internal/v1/profiles/{harness.user_id}", headers=HEADERS, json=BODY
        )
    assert result.status_code == 503
    assert harness.profiles._rows == harness.settings._rows == {}


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"registered_at": "2026-01-01T00:00:00"},
        {**BODY, "display_name": "Injected"},
    ],
)
def test_provision_validates_registration_contract(client, harness, body):
    assert (
        client.put(
            f"/internal/v1/profiles/{harness.user_id}", headers=HEADERS, json=body
        ).status_code
        == 422
    )
    assert harness.profiles._rows == harness.settings._rows == {}

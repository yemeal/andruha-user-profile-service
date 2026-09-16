"""Settings contracts with signed JWT and the production command bus."""

import pytest
from tests.integration.http_support import client as client
from tests.integration.http_support import harness as harness
from tests.integration.http_support import tokens as tokens

pytestmark = pytest.mark.integration


def test_settings_require_authentication(client):
    assert client.get("/api/v1/settings/me").status_code == 401


def test_settings_get_reads_existing_settings(client, harness, tokens):
    harness.seed_settings()
    response = client.get(
        "/api/v1/settings/me", headers=tokens.authorization(harness.user_id)
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(harness.user_id)
    assert data["theme"] == "system" and data["locale"] == "ru"
    assert data["timezone"] == "Europe/Moscow"
    assert all(value == "ALL" for value in data["privacy"].values())
    assert response.headers["etag"] == '"1"'
    assert response.headers["cache-control"] == "private, no-cache"
    assert harness.profiles._rows == {}


def test_settings_get_does_not_create_missing_rows(client, harness, tokens):
    response = client.get(
        "/api/v1/settings/me", headers=tokens.authorization(harness.user_id)
    )
    assert response.status_code == 404
    assert harness.profiles._rows == harness.settings._rows == {}


def test_settings_patch_returns_404_when_missing(client, harness, tokens):
    response = client.patch(
        "/api/v1/settings/me",
        headers=tokens.mutation(harness.user_id),
        json={"theme": "dark"},
    )
    assert response.status_code == 404
    assert harness.profiles._rows == harness.settings._rows == {}


def test_settings_patch_merges_privacy_and_replays(client, harness, tokens):
    harness.seed_profile()
    harness.seed_settings(
        privacy={
            "who_can_see_avatar": "NOBODY",
            "who_can_see_bio": "ALL",
            "who_can_find_by_username": "ALL",
        }
    )
    headers = tokens.mutation(harness.user_id)
    payload = {
        "theme": "dark",
        "locale": "en",
        "timezone": "America/New_York",
        "privacy": {"who_can_see_bio": "NOBODY"},
    }
    response = client.patch("/api/v1/settings/me", headers=headers, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["theme"] == "dark" and data["locale"] == "en"
    assert data["timezone"] == "America/New_York"
    assert data["privacy"] == {
        "who_can_see_avatar": "NOBODY",
        "who_can_see_bio": "NOBODY",
        "who_can_find_by_username": "ALL",
    }
    assert data["version"] == 2 and response.headers["etag"] == '"2"'
    replay = client.patch("/api/v1/settings/me", headers=headers, json=payload)
    assert replay.status_code == 200 and replay.json() == data
    assert (
        client.patch(
            "/api/v1/settings/me", headers=headers, json={"theme": "light"}
        ).status_code
        == 409
    )


def test_settings_stale_patch(client, harness, tokens):
    harness.seed_settings(theme="dark", version=2)
    response = client.patch(
        "/api/v1/settings/me",
        headers=tokens.mutation(harness.user_id),
        json={"theme": "light"},
    )
    assert response.status_code == 409
    assert response.json()["parameters"]["current_version"] == 2
    assert harness.settings._rows[harness.user_id].theme == "dark"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"theme": "neon"},
        {"locale": "invalid_locale"},
        {"timezone": "Invalid/Zone"},
        {"privacy": {}},
        {"privacy": {"who_can_see_bio": None}},
        {"privacy": {"who_can_see_bio": "CONTACTS"}},
        {"privacy": {"unknown": "ALL"}},
        {"theme": None},
        {"privacy": None},
        {"password": "secret"},
        {"who_can_see_bio": "NOBODY"},
    ],
)
def test_invalid_settings_does_not_mutate(client, harness, tokens, payload):
    harness.seed_settings(theme="dark")
    response = client.patch(
        "/api/v1/settings/me", headers=tokens.mutation(harness.user_id), json=payload
    )
    assert response.status_code == 422
    assert harness.settings._rows[harness.user_id].theme == "dark"
    assert harness.settings._rows[harness.user_id].version == 1


def test_unchanged_settings_keep_version(client, harness, tokens):
    harness.seed_settings(theme="dark")
    response = client.patch(
        "/api/v1/settings/me",
        headers=tokens.mutation(harness.user_id),
        json={"theme": "dark"},
    )
    assert response.status_code == 200 and response.json()["version"] == 1

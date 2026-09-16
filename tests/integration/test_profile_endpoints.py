"""Writes, search and existence through real JWT and command dispatch."""

from uuid import uuid4

import pytest
from tests.integration.http_support import client as client
from tests.integration.http_support import harness as harness
from tests.integration.http_support import tokens as tokens

pytestmark = pytest.mark.integration


def test_profile_patch_replay_and_conflict(client, harness, tokens):
    harness.seed_profile()
    auth = tokens.authorization(harness.user_id)
    assert client.get("/api/v1/profiles/me", headers=auth).status_code == 200
    headers = tokens.mutation(harness.user_id)
    payload = {
        "display_name": "Alex Smith",
        "bio": "Biography",
        "username": "super_coder",
    }
    response = client.patch("/api/v1/profiles/me", headers=headers, json=payload)
    assert response.status_code == 200
    assert response.json()["version"] == 2
    assert response.json()["display_name"] == "Alex Smith"
    assert response.headers["etag"] == '"2"'
    replay = client.patch("/api/v1/profiles/me", headers=headers, json=payload)
    assert replay.status_code == 200 and replay.json() == response.json()
    assert replay.headers["etag"] == response.headers["etag"]
    assert client.get("/api/v1/profiles/me", headers=auth).json()["version"] == 2
    assert (
        client.patch(
            "/api/v1/profiles/me", headers=headers, json={"bio": "Different"}
        ).status_code
        == 409
    )


def test_profile_noop_and_stale_version(client, harness, tokens):
    harness.seed_profile(display_name="Original", version=3)
    result = client.patch(
        "/api/v1/profiles/me",
        headers=tokens.mutation(harness.user_id, version=3),
        json={"display_name": "Original"},
    )
    assert result.status_code == 200 and result.json()["version"] == 3
    stale = client.patch(
        "/api/v1/profiles/me",
        headers=tokens.mutation(harness.user_id),
        json={"display_name": "Overwrite"},
    )
    assert stale.status_code == 409
    assert stale.json()["parameters"]["current_version"] == 3
    assert harness.profiles._rows[harness.user_id].display_name == "Original"


@pytest.mark.parametrize(
    "etag, status",
    [
        (None, 428),
        ('W/"1"', 400),
        ('"0"', 400),
        ('"-1"', 400),
        ("1", 400),
        ("*", 400),
        ('"1", "2"', 400),
        ('"9223372036854775808"', 400),
    ],
)
@pytest.mark.parametrize("resource", ["profiles", "settings"])
def test_patch_version_headers(client, harness, tokens, etag, status, resource):
    headers = tokens.mutation(harness.user_id)
    if etag is None:
        del headers["If-Match"]
    else:
        headers["If-Match"] = etag
    body = {"bio": "New"} if resource == "profiles" else {"theme": "dark"}
    assert (
        client.patch(f"/api/v1/{resource}/me", headers=headers, json=body).status_code
        == status
    )
    assert harness.profiles._rows == harness.settings._rows == {}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"display_name": None},
        {"username": None},
        {"display_name": "Alex \U0001f60a"},
        {"display_name": "   "},
        {"bio": "line\nbreak"},
        {"username": "admin"},
        {"username": "invalid name"},
        {"display_name": "Valid", "email": "private@example.com"},
        {"user_id": str(uuid4())},
        {"version": 1},
        {"avatar_key": "any"},
    ],
)
def test_profile_invalid_input_is_atomic(client, harness, tokens, payload):
    harness.seed_profile(display_name="Original")
    response = client.patch(
        "/api/v1/profiles/me", headers=tokens.mutation(harness.user_id), json=payload
    )
    assert response.status_code == 422
    assert harness.profiles._rows[harness.user_id].display_name == "Original"
    assert harness.profiles._rows[harness.user_id].version == 1


@pytest.mark.parametrize("value", [None, ""])
def test_explicit_bio_clear(client, harness, tokens, value):
    harness.seed_profile(bio="Old bio")
    response = client.patch(
        "/api/v1/profiles/me",
        headers=tokens.mutation(harness.user_id),
        json={"bio": value},
    )
    assert response.status_code == 200 and response.json()["bio"] is None


def test_username_collision_rolls_back(client, harness, tokens):
    harness.seed_profile(display_name="Original")
    harness.seed_profile(user_id=harness.other_user_id, username="taken_name")
    response = client.patch(
        "/api/v1/profiles/me",
        headers=tokens.mutation(harness.user_id),
        json={"display_name": "Changed", "username": "taken_name"},
    )
    assert response.status_code == 409
    assert harness.profiles._rows[harness.user_id].display_name == "Original"


@pytest.mark.parametrize(
    "resource, payload", [("profiles", {"bio": "New"}), ("settings", {"theme": "dark"})]
)
def test_patch_requires_jwt_and_key(client, harness, tokens, resource, payload):
    url = f"/api/v1/{resource}/me"
    assert client.patch(url, json=payload).status_code == 401
    headers = tokens.authorization(harness.user_id) | {"If-Match": '"1"'}
    assert client.patch(url, headers=headers, json=payload).status_code == 422
    for key in ("", "x" * 256):
        headers["Idempotency-Key"] = key
        assert client.patch(url, headers=headers, json=payload).status_code == 422


def test_actor_scopes_mutations_and_idempotency(client, harness, tokens):
    for user_id in (harness.user_id, harness.other_user_id):
        harness.seed_profile(user_id=user_id)
        result = client.patch(
            "/api/v1/profiles/me",
            params={"user_id": str(harness.other_user_id)},
            headers=tokens.mutation(user_id, key="same-key"),
            json={"bio": str(user_id)},
        )
        assert result.status_code == 200 and result.json()["user_id"] == str(user_id)
    assert harness.profiles._rows[harness.user_id].bio == str(harness.user_id)


def test_search_normalizes_username_and_applies_privacy(client, harness, tokens):
    harness.seed_profile(username="super_coder")
    harness.seed_settings()
    for name in ("super_coder", "SUPER_CODER"):
        response = client.get("/api/v1/profiles", params={"username": name})
        assert (
            response.status_code == 200 and response.json()["username"] == "super_coder"
        )
        assert response.headers["cache-control"] == "no-store"
    response = client.patch(
        "/api/v1/settings/me",
        headers=tokens.mutation(harness.user_id),
        json={"privacy": {"who_can_find_by_username": "NOBODY"}},
    )
    assert response.status_code == 200
    assert client.get("/api/v1/profiles?username=super_coder").status_code == 404
    assert (
        client.get(
            "/api/v1/profiles?username=super_coder",
            headers=tokens.authorization(harness.user_id),
        ).status_code
        == 200
    )
    assert client.get("/api/v1/profiles?username=unknown_user").status_code == 404


@pytest.mark.parametrize(
    "query", ["", "?username=x", "?username=invalid!", "?username=admin"]
)
def test_search_validates_username(client, query):
    assert client.get("/api/v1/profiles" + query).status_code == 422


def test_internal_head_and_public_reads_never_provision(client, harness, tokens):
    url = f"/internal/v1/profiles/{harness.user_id}"
    missing = client.head(url)
    assert missing.status_code == 404 and missing.content == b""
    assert client.get(f"/api/v1/profiles/{harness.user_id}").status_code == 404
    assert harness.profiles._rows == {}
    assert (
        client.get(
            "/api/v1/profiles/me", headers=tokens.authorization(harness.user_id)
        ).status_code
        == 404
    )
    harness.seed_profile()
    exists = client.head(url)
    assert exists.status_code == 200 and exists.content == b""
    assert exists.headers["cache-control"] == "no-store"
    assert client.head("/internal/v1/profiles/invalid").status_code == 422


@pytest.mark.parametrize("missing", ["profiles", "settings"])
def test_reads_preserve_remaining_data_when_one_row_is_missing(
    client, harness, tokens, missing
):
    headers = tokens.authorization(harness.user_id)
    harness.seed_profile(display_name="Keep Name", version=4)
    harness.seed_settings(theme="dark", version=6)
    repository = harness.profiles if missing == "profiles" else harness.settings
    del repository._rows[harness.user_id]
    first = client.get(f"/api/v1/{missing}/me", headers=headers)
    assert first.status_code == 404
    if missing == "profiles":
        assert harness.settings._rows[harness.user_id].theme == "dark"
        assert harness.settings._rows[harness.user_id].version == 6
    else:
        assert harness.profiles._rows[harness.user_id].display_name == "Keep Name"
        assert harness.profiles._rows[harness.user_id].version == 4
    assert harness.user_id not in repository._rows

"""HTTP reads through real authentication and application handlers."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from tests.integration.http_support import Tokens, profile_client
from tests.integration.http_support import client as client
from tests.integration.http_support import harness as harness
from tests.integration.http_support import tokens as tokens
from tests.unit.application.support import HandlerHarness

from app.core.settings import JWTSettings
from app.domain.value_objects.privacy import PrivacyScope, PrivacySettings

pytestmark = pytest.mark.integration
PUBLIC_FIELDS = {
    "user_id",
    "username",
    "display_name",
    "bio",
    "avatar_key",
    "is_verified",
}


def seed_private_profile(harness: HandlerHarness, user_id: UUID) -> None:
    harness.seed_profile(
        user_id=user_id, bio="Private biography", avatar_key="avatars/private.png"
    )
    harness.seed_settings(
        user_id=user_id,
        privacy=PrivacySettings(
            who_can_see_bio=PrivacyScope.NOBODY,
            who_can_see_avatar=PrivacyScope.NOBODY,
        ),
    )


@pytest.mark.parametrize("role", ["USER", "ADMIN"])
def test_me_uses_verified_subject_and_returns_complete_profile(
    client: TestClient, harness: HandlerHarness, tokens: Tokens, role: str
) -> None:
    seed_private_profile(harness, harness.user_id)
    harness.seed_profile(user_id=harness.other_user_id, display_name="Another User")
    response = client.get(
        "/api/v1/profiles/me",
        params={"user_id": str(harness.other_user_id)},
        headers={
            **tokens.authorization(harness.user_id, claims={"role": role}),
            "X-Request-Id": "profile-read",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(harness.user_id)
    assert data["bio"] == "Private biography"
    assert data["avatar_key"] == "avatars/private.png"
    assert data["version"] == 1
    assert "status" in data and "created_at" in data
    assert response.headers["etag"] == '"1"'
    assert response.headers["cache-control"] == "private, no-cache"
    assert response.headers["x-request-id"] == "profile-read"


def test_me_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/profiles/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_does_not_create_missing_profile_and_settings(
    client: TestClient, harness: HandlerHarness, tokens: Tokens
) -> None:
    for _ in range(2):
        response = client.get(
            "/api/v1/profiles/me", headers=tokens.authorization(harness.user_id)
        )
        assert response.status_code == 404
    assert harness.profiles._rows == harness.settings._rows == {}


@pytest.mark.parametrize("viewer", ["anonymous", "other", "owner"])
def test_public_profile_applies_privacy_for_verified_viewer(
    client: TestClient, harness: HandlerHarness, tokens: Tokens, viewer: str
) -> None:
    seed_private_profile(harness, harness.user_id)
    headers = (
        {}
        if viewer == "anonymous"
        else tokens.authorization(
            harness.user_id if viewer == "owner" else harness.other_user_id
        )
    )
    response = client.get(
        f"/api/v1/profiles/{harness.user_id}",
        params={"viewer_id": str(harness.user_id)},
        headers={**headers, "X-User-Id": str(harness.user_id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert set(data) == PUBLIC_FIELDS
    assert data["user_id"] == str(harness.user_id)
    assert data["bio"] == ("Private biography" if viewer == "owner" else None)
    assert data["avatar_key"] == ("avatars/private.png" if viewer == "owner" else None)
    assert response.headers["cache-control"] == "no-store"


def test_public_profile_with_default_privacy_is_visible(
    client: TestClient, harness: HandlerHarness
) -> None:
    harness.seed_profile(bio="Public biography", avatar_key="avatars/public.png")
    harness.seed_settings()
    response = client.get(f"/api/v1/profiles/{harness.user_id}")
    assert response.status_code == 200
    assert response.json()["bio"] == "Public biography"
    assert response.json()["avatar_key"] == "avatars/public.png"


def test_public_profile_missing_returns_404(client: TestClient) -> None:
    assert client.get(f"/api/v1/profiles/{uuid4()}").status_code == 404


def test_public_profile_invalid_id_returns_422(client: TestClient) -> None:
    assert client.get("/api/v1/profiles/not-a-uuid").status_code == 422


@pytest.mark.parametrize("authenticated", [False, True])
def test_batch_preserves_order_deduplicates_omits_missing_and_applies_privacy(
    client: TestClient, harness: HandlerHarness, tokens: Tokens, authenticated: bool
) -> None:
    seed_private_profile(harness, harness.user_id)
    seed_private_profile(harness, harness.other_user_id)
    response = client.post(
        "/api/v1/profiles/batch",
        json={
            "user_ids": [
                str(harness.other_user_id),
                str(uuid4()),
                str(harness.user_id),
                str(harness.other_user_id),
            ]
        },
        headers=tokens.authorization(harness.user_id) if authenticated else {},
    )
    assert response.status_code == 200
    other, own = response.json()
    assert [other["user_id"], own["user_id"]] == [
        str(harness.other_user_id),
        str(harness.user_id),
    ]
    assert set(other) == set(own) == PUBLIC_FIELDS
    assert other["bio"] is None and other["avatar_key"] is None
    assert own["bio"] == ("Private biography" if authenticated else None)
    assert own["avatar_key"] == ("avatars/private.png" if authenticated else None)
    assert response.headers["cache-control"] == "no-store"


def test_batch_accepts_100_and_returns_empty_when_all_missing(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/profiles/batch", json={"user_ids": [str(uuid4()) for _ in range(100)]}
    )
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"user_ids": []},
        {"user_ids": ["invalid"]},
        {"user_ids": "not-a-list"},
        {"user_ids": [str(uuid4())] * 101},
        {"user_ids": [str(uuid4())], "viewer_id": str(uuid4())},
    ],
)
def test_batch_rejects_invalid_payload(client: TestClient, payload: Any) -> None:
    assert client.post("/api/v1/profiles/batch", json=payload).status_code == 422


@pytest.mark.parametrize("batch", [False, True])
def test_missing_privacy_settings_fail_closed(
    client: TestClient, harness: HandlerHarness, batch: bool
) -> None:
    harness.seed_profile(bio="Secret biography", avatar_key="secret/key")
    response = (
        client.post("/api/v1/profiles/batch", json={"user_ids": [str(harness.user_id)]})
        if batch
        else client.get(f"/api/v1/profiles/{harness.user_id}")
    )
    assert response.status_code == 503
    assert "Secret biography" not in response.text
    assert "secret/key" not in response.text
    assert "UserSettingsNotFound" not in response.text


@pytest.mark.parametrize(
    "claims",
    [
        {"exp": 1},
        {"iat": 4_102_444_800},
        {"iss": "attacker"},
        {"aud": "another-service"},
        {"sub": "not-a-uuid"},
        {"role": "SUPERUSER"},
        {"role": ["USER"]},
        {"jti": "not-a-uuid"},
    ],
)
def test_rejects_invalid_signed_claims(
    client: TestClient, harness: HandlerHarness, tokens: Tokens, claims: dict[str, Any]
) -> None:
    response = client.get(
        "/api/v1/profiles/me",
        headers=tokens.authorization(harness.user_id, claims=claims),
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("claim", ["iss", "aud", "sub", "iat", "exp", "jti", "role"])
def test_rejects_missing_required_claim(
    client: TestClient, harness: HandlerHarness, tokens: Tokens, claim: str
) -> None:
    response = client.get(
        "/api/v1/profiles/me", headers=tokens.authorization(harness.user_id, omit=claim)
    )
    assert response.status_code == 401


@pytest.mark.parametrize("headers", [{"kid": "untrusted-key"}, {"typ": "JWT"}])
def test_rejects_untrusted_key_id_and_wrong_token_type(
    client: TestClient, harness: HandlerHarness, tokens: Tokens, headers: dict[str, str]
) -> None:
    response = client.get(
        "/api/v1/profiles/me",
        headers=tokens.authorization(harness.user_id, headers=headers),
    )
    assert response.status_code == 401


@pytest.mark.parametrize("algorithm", ["RS256", "HS256", "none"])
def test_rejects_forged_signature_and_unapproved_algorithms(
    client: TestClient, harness: HandlerHarness, tokens: Tokens, algorithm: str
) -> None:
    key = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        if algorithm == "RS256"
        else "attacker-controlled-secret-at-least-32-bytes"
        if algorithm == "HS256"
        else ""
    )
    response = client.get(
        "/api/v1/profiles/me",
        headers=tokens.authorization(harness.user_id, key=key, algorithm=algorithm),
    )
    assert response.status_code == 401


@pytest.mark.parametrize("authorization", ["Bearer broken", "Bearer", "Basic abc"])
def test_public_reads_reject_supplied_invalid_credentials(
    client: TestClient, harness: HandlerHarness, authorization: str
) -> None:
    seed_private_profile(harness, harness.user_id)
    headers = {"Authorization": authorization, "X-Request-Id": "invalid-auth"}
    responses = [
        client.get(f"/api/v1/profiles/{harness.user_id}", headers=headers),
        client.post(
            "/api/v1/profiles/batch",
            headers=headers,
            json={"user_ids": [str(harness.user_id)]},
        ),
    ]
    for response in responses:
        assert response.status_code == 401
        assert response.headers["x-request-id"] == "invalid-auth"
        assert "Private biography" not in response.text


def test_unconfigured_auth_does_not_block_anonymous_reads(
    harness: HandlerHarness, tokens: Tokens
) -> None:
    harness.seed_profile()
    harness.seed_settings()
    with profile_client(harness, JWTSettings(public_keys={})) as client:
        assert client.get(f"/api/v1/profiles/{harness.user_id}").status_code == 200
        assert client.get("/api/v1/profiles/me").status_code == 401
        response = client.get(
            "/api/v1/profiles/me", headers=tokens.authorization(harness.user_id)
        )
        assert response.status_code == 503

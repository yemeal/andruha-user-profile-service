"""Integration tests for UserProfile HTTP endpoints (FastAPI)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.entrypoints.http.main import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    """Helper to mock authenticated request headers/cookies."""
    return {"Authorization": f"Bearer mock_token_for_{user_id}"}


@pytest.mark.integration
class TestGetOwnProfileEndpoint:
    """Tests for GET /api/v1/profiles/me."""

    def test_get_own_profile_unauthorized_without_token(
        self, client: TestClient
    ) -> None:
        response = client.get("/api/v1/profiles/me")
        assert response.status_code == 401

    def test_get_own_profile_returns_etag_and_cache_control(
        self, client: TestClient
    ) -> None:
        user_id = uuid.uuid4()
        response = client.get(
            "/api/v1/profiles/me",
            headers=auth_headers(user_id),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == str(user_id)
        assert data["display_name"] == "Пользователь"
        assert data["version"] == 1
        assert "ETag" in response.headers
        assert response.headers["ETag"].strip('"') == "1"
        assert "no-cache" in response.headers.get("Cache-Control", "")


@pytest.mark.integration
class TestPatchOwnProfileEndpoint:
    """Tests for PATCH /api/v1/profiles/me."""

    def test_patch_without_if_match_returns_428_precondition_required(
        self, client: TestClient
    ) -> None:
        user_id = uuid.uuid4()
        response = client.patch(
            "/api/v1/profiles/me",
            json={"display_name": "New Name"},
            headers=auth_headers(user_id),
            # Missing If-Match header
        )

        assert response.status_code == 428

    def test_patch_with_stale_if_match_returns_409_conflict(
        self, client: TestClient
    ) -> None:
        user_id = uuid.uuid4()
        # Initialize profile (version 1)
        client.get("/api/v1/profiles/me", headers=auth_headers(user_id))

        # Stale If-Match: "0" instead of "1"
        response = client.patch(
            "/api/v1/profiles/me",
            json={"display_name": "New Name"},
            headers={**auth_headers(user_id), "If-Match": '"0"'},
        )

        assert response.status_code == 409
        data = response.json()
        assert data.get("current_version") == 1 or "version" in str(data)

    def test_patch_with_invalid_display_name_returns_422(
        self, client: TestClient
    ) -> None:
        user_id = uuid.uuid4()
        response = client.patch(
            "/api/v1/profiles/me",
            json={"display_name": "Alex 😊"},  # emoji forbidden
            headers={**auth_headers(user_id), "If-Match": '"1"'},
        )

        assert response.status_code == 422

    def test_patch_with_credential_fields_rejected(self, client: TestClient) -> None:
        user_id = uuid.uuid4()
        # Attempting to inject email / password into profile
        response = client.patch(
            "/api/v1/profiles/me",
            json={"email": "attacker@example.com", "display_name": "Valid Name"},
            headers={**auth_headers(user_id), "If-Match": '"1"'},
        )

        assert response.status_code == 422

    def test_patch_success_returns_updated_profile_and_new_etag(
        self, client: TestClient
    ) -> None:
        user_id = uuid.uuid4()
        # 1. GET initial profile
        get_res = client.get("/api/v1/profiles/me", headers=auth_headers(user_id))
        assert get_res.status_code == 200
        initial_etag = get_res.headers["ETag"]

        # 2. PATCH profile
        patch_res = client.patch(
            "/api/v1/profiles/me",
            json={
                "display_name": "Алексей Смирнов",
                "bio": "Building reliable distributed systems",
                "username": "alex_smirnov",
            },
            headers={**auth_headers(user_id), "If-Match": initial_etag},
        )

        assert patch_res.status_code == 200
        updated = patch_res.json()
        assert updated["display_name"] == "Алексей Смирнов"
        assert updated["bio"] == "Building reliable distributed systems"
        assert updated["username"] == "alex_smirnov"
        assert updated["version"] == 2
        assert patch_res.headers["ETag"].strip('"') == "2"


@pytest.mark.integration
class TestPublicProfileEndpoints:
    """Tests for public reads, search, batch, and internal HEAD check."""

    def test_get_public_profile_by_id(self, client: TestClient) -> None:
        user_id = uuid.uuid4()
        # Create user profile
        client.get("/api/v1/profiles/me", headers=auth_headers(user_id))

        # Query public profile
        res = client.get(f"/api/v1/profiles/{user_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["user_id"] == str(user_id)
        assert data["display_name"] == "Пользователь"
        assert "password" not in data
        assert "email" not in data

    def test_get_public_profile_not_found(self, client: TestClient) -> None:
        unknown_id = uuid.uuid4()
        res = client.get(f"/api/v1/profiles/{unknown_id}")
        assert res.status_code == 404

    def test_search_profile_by_username_exact_match(self, client: TestClient) -> None:
        user_id = uuid.uuid4()
        # Update username to custom
        client.get("/api/v1/profiles/me", headers=auth_headers(user_id))
        client.patch(
            "/api/v1/profiles/me",
            json={"username": "super_coder"},
            headers={**auth_headers(user_id), "If-Match": '"1"'},
        )

        # Search by lowercase and uppercase query
        res = client.get("/api/v1/profiles?username=super_coder")
        assert res.status_code == 200
        assert res.json()["username"] == "super_coder"

        res_case = client.get("/api/v1/profiles?username=SUPER_CODER")
        assert res_case.status_code == 200
        assert res_case.json()["username"] == "super_coder"

        # Non-existing username
        res_not_found = client.get("/api/v1/profiles?username=unknown_user")
        assert res_not_found.status_code == 404

    def test_batch_profiles_endpoint(self, client: TestClient) -> None:
        u1 = uuid.uuid4()
        u2 = uuid.uuid4()
        client.get("/api/v1/profiles/me", headers=auth_headers(u1))
        client.get("/api/v1/profiles/me", headers=auth_headers(u2))

        res = client.post(
            "/api/v1/profiles/batch",
            json={"user_ids": [str(u1), str(u2)]},
        )
        assert res.status_code == 200
        items = res.json()
        assert len(items) == 2

    def test_batch_profiles_exceeding_100_rejected(self, client: TestClient) -> None:
        ids = [str(uuid.uuid4()) for _ in range(101)]
        res = client.post(
            "/api/v1/profiles/batch",
            json={"user_ids": ids},
        )
        assert res.status_code == 422

    def test_internal_head_profile_check(self, client: TestClient) -> None:
        user_id = uuid.uuid4()
        # Before creation -> 404
        head_missing = client.head(f"/internal/v1/profiles/{user_id}")
        assert head_missing.status_code == 404

        # Provision profile
        client.get("/api/v1/profiles/me", headers=auth_headers(user_id))

        # After creation -> 200
        head_exists = client.head(f"/internal/v1/profiles/{user_id}")
        assert head_exists.status_code == 200

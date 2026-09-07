"""Integration tests for UserSettings HTTP endpoints (FastAPI)."""

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
    return {"Authorization": f"Bearer mock_token_for_{user_id}"}


@pytest.mark.integration
class TestUserSettingsEndpoints:
    """Tests for GET and PATCH /api/v1/settings/me."""

    def test_get_settings_unauthorized_without_token(self, client: TestClient) -> None:
        response = client.get("/api/v1/settings/me")
        assert response.status_code == 401

    def test_get_settings_returns_defaults_lazy_provisioned(
        self, client: TestClient
    ) -> None:
        user_id = uuid.uuid4()
        response = client.get(
            "/api/v1/settings/me",
            headers=auth_headers(user_id),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == str(user_id)
        assert data["theme"] == "system"
        assert data["locale"] == "ru"
        assert data["timezone"] == "Europe/Moscow"
        assert data["privacy"]["who_can_see_avatar"] == "ALL"
        assert data["privacy"]["who_can_find_by_username"] == "ALL"
        assert data["privacy"]["who_can_see_bio"] == "ALL"

    def test_patch_settings_success(self, client: TestClient) -> None:
        user_id = uuid.uuid4()
        # Initialize
        client.get("/api/v1/settings/me", headers=auth_headers(user_id))

        response = client.patch(
            "/api/v1/settings/me",
            json={
                "theme": "dark",
                "locale": "en",
                "timezone": "America/New_York",
                "privacy": {
                    "who_can_see_avatar": "NOBODY",
                    "who_can_find_by_username": "ALL",
                    "who_can_see_bio": "NOBODY",
                },
            },
            headers=auth_headers(user_id),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["theme"] == "dark"
        assert data["locale"] == "en"
        assert data["timezone"] == "America/New_York"
        assert data["privacy"]["who_can_see_avatar"] == "NOBODY"
        assert data["privacy"]["who_can_see_bio"] == "NOBODY"

    def test_patch_settings_invalid_locale_returns_422(
        self, client: TestClient
    ) -> None:
        user_id = uuid.uuid4()
        response = client.patch(
            "/api/v1/settings/me",
            json={"locale": "invalid_locale"},
            headers=auth_headers(user_id),
        )

        assert response.status_code == 422

    def test_patch_settings_invalid_theme_returns_422(self, client: TestClient) -> None:
        user_id = uuid.uuid4()
        response = client.patch(
            "/api/v1/settings/me",
            json={"theme": "neon"},
            headers=auth_headers(user_id),
        )

        assert response.status_code == 422

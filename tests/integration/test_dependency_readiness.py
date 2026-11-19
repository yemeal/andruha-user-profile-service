import pytest
from fastapi.testclient import TestClient
from tests.integration.http_support import tokens as tokens

from app.entrypoints.http.main import create_app


def test_unavailable_database_is_not_ready_but_process_stays_live(monkeypatch, tokens):
    monkeypatch.setenv("POSTGRES_HOST", "127.0.0.1")
    monkeypatch.setenv("POSTGRES_PORT", "1")
    monkeypatch.setenv(
        "JWT_PUBLIC_KEYS",
        '{"test-key":"' + tokens.settings.public_keys["test-key"].as_posix() + '"}',
    )
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        assert client.get("/health/live").status_code == 200
        ready = client.get("/health/ready")
        assert ready.status_code == 503
        assert ready.json() == {"status": "unavailable"}


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/api/v1/profiles/00000000-0000-4000-8000-000000000001", None),
        ("GET", "/api/v1/profiles?username=alice", None),
        (
            "POST",
            "/api/v1/profiles/batch",
            {"user_ids": ["00000000-0000-4000-8000-000000000001"]},
        ),
    ],
)
def test_database_outage_returns_safe_business_unavailable(
    monkeypatch, tokens, method, path, body
):
    monkeypatch.setenv("POSTGRES_HOST", "127.0.0.1")
    monkeypatch.setenv("POSTGRES_PORT", "1")
    monkeypatch.setenv(
        "JWT_PUBLIC_KEYS",
        '{"test-key":"' + tokens.settings.public_keys["test-key"].as_posix() + '"}',
    )
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        response = client.request(method, path, json=body)

    assert response.status_code == 503
    assert response.json() == {"detail": "Profile temporarily unavailable"}
    assert "postgres" not in response.text.lower()

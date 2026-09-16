"""Configuration and key-loading guarantees at the HTTP authentication boundary."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from pydantic import ValidationError

from app.core.settings import JWTSettings
from app.entrypoints.http.security import AccessTokenVerifier


@pytest.fixture(scope="module")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def write_public_key(path, key):
    path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    return path


def test_settings_load_key_ring_from_environment(monkeypatch, tmp_path):
    import json

    path = tmp_path / "identity.pem"
    monkeypatch.setenv("JWT_PUBLIC_KEYS", json.dumps({"identity-v1": str(path)}))
    monkeypatch.setenv("JWT_ISSUER", "trusted-issuer")
    monkeypatch.setenv("JWT_AUDIENCE", "profile-service")
    monkeypatch.setenv("JWT_CLOCK_SKEW_SECONDS", "5")
    settings = JWTSettings(_env_file=None)
    assert settings.public_keys == {"identity-v1": path}
    assert settings.issuer == "trusted-issuer"
    assert settings.audience == "profile-service"
    assert settings.clock_skew_seconds == 5


@pytest.mark.parametrize(
    "overrides",
    [
        {"issuer": " "},
        {"audience": ""},
        {"clock_skew_seconds": -1},
        {"public_keys": {" ": Path("ignored.pem")}},
    ],
)
def test_invalid_verifier_settings_are_rejected(overrides):
    with pytest.raises(ValidationError):
        JWTSettings(_env_file=None, **overrides)


def test_empty_key_ring_cannot_construct_verifier():
    with pytest.raises(ValueError, match="trusted public key"):
        AccessTokenVerifier(JWTSettings(public_keys={}, _env_file=None))


def test_missing_configured_key_is_not_silently_ignored(tmp_path):
    with pytest.raises(FileNotFoundError):
        AccessTokenVerifier(JWTSettings(public_keys={"key": tmp_path / "missing.pem"}))


@pytest.mark.parametrize("key_type", ["ec", "weak-rsa", "private", "garbage"])
def test_only_strong_public_rsa_keys_are_accepted(key_type, rsa_key, tmp_path):
    path = tmp_path / "key.pem"
    if key_type == "ec":
        write_public_key(path, ec.generate_private_key(ec.SECP256R1()))
    elif key_type == "weak-rsa":
        write_public_key(
            path, rsa.generate_private_key(public_exponent=65537, key_size=1024)
        )
    elif key_type == "private":
        path.write_bytes(
            rsa_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    else:
        path.write_text("not a key", encoding="utf-8")
    with pytest.raises(ValueError):
        AccessTokenVerifier(JWTSettings(public_keys={"key": path}))


def test_verifier_preloads_keys_and_accepts_trusted_rotation_keys(rsa_key, tmp_path):
    path = write_public_key(tmp_path / "key.pem", rsa_key)
    settings = JWTSettings(public_keys={"old": path, "new": path})
    verifier = AccessTokenVerifier(settings)
    path.unlink()
    settings.public_keys.clear()
    user_id = uuid4()
    now = datetime.now(UTC).timestamp()
    for key_id in ("old", "new"):
        token = jwt.encode(
            {
                "iss": settings.issuer,
                "aud": settings.audience,
                "sub": str(user_id),
                "jti": str(uuid4()),
                "role": "USER",
                "iat": now,
                "exp": now + 300,
            },
            rsa_key,
            algorithm="RS256",
            headers={"typ": "at+jwt", "kid": key_id},
        )
        assert verifier.verify(token) == user_id

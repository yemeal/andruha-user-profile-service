import os

import pytest

from app.application.exceptions.idempotency import StoredReplayUnavailableError
from app.infrastructure.idempotency.security.stored_result_protector import (
    AESGCMStoredResultProtector,
)


def test_protect_and_restore_success():
    key_id = "v1"
    key_bytes = os.urandom(32)
    protector = AESGCMStoredResultProtector(
        active_key_id=key_id,
        keys={key_id: key_bytes},
    )

    payload = {"secret_token": "abc-123", "sub": "user-456"}
    aad = b"authenticated-context-data"

    envelope = protector.protect(payload, aad=aad)
    assert envelope["version"] == 1
    assert envelope["algorithm"] == "AES-256-GCM"
    assert envelope["key_id"] == key_id
    assert "nonce" in envelope
    assert "ciphertext" in envelope

    restored = protector.restore(envelope, aad=aad)
    assert restored == payload


def test_restore_tampered_ciphertext_fails():
    key_id = "v1"
    key_bytes = os.urandom(32)
    protector = AESGCMStoredResultProtector(
        active_key_id=key_id,
        keys={key_id: key_bytes},
    )

    envelope = protector.protect({"secret": "val"}, aad=b"aad")
    # Wrong AAD
    with pytest.raises(StoredReplayUnavailableError):
        protector.restore(envelope, aad=b"wrong-aad")


def test_key_rotation_support():
    k1 = os.urandom(32)
    k2 = os.urandom(32)

    # Protect with old key k1
    protector1 = AESGCMStoredResultProtector(
        active_key_id="v1",
        keys={"v1": k1},
    )
    envelope = protector1.protect({"data": "payload"}, aad=b"context")

    # Ring with v2 as active, but still knows v1
    protector2 = AESGCMStoredResultProtector(
        active_key_id="v2",
        keys={"v1": k1, "v2": k2},
    )
    restored = protector2.restore(envelope, aad=b"context")
    assert restored == {"data": "payload"}

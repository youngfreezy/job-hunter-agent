# Copyright (c) 2026 V2 Software LLC. All rights reserved.

"""Isolated test for resume persistence across deploys.

Verifies the encrypt → save-to-Postgres → delete-from-disk → recover-from-Postgres
flow that protects against Railway's ephemeral /tmp filesystem.
"""

import os
import tempfile
import uuid

import pytest

import backend.shared.resume_crypto as _crypto


@pytest.fixture(autouse=True)
def _set_nextauth_secret(monkeypatch):
    """Ensure NEXTAUTH_SECRET is set for Fernet key derivation in CI."""
    monkeypatch.setenv("NEXTAUTH_SECRET", "test-secret-for-ci")
    # Reset the cached Fernet instance so it re-derives from the new secret
    _crypto._fernet = None
    yield
    _crypto._fernet = None


from backend.shared.resume_crypto import encrypt_and_save, decrypt_to_bytes, _get_fernet
from backend.shared.resume_store import save_resume, get_resume, delete_resume


@pytest.fixture
def sample_resume_bytes():
    """A minimal valid PDF header for testing."""
    return b"%PDF-1.4 fake resume content for testing persistence"


@pytest.fixture
def encrypted_resume_file(sample_resume_bytes):
    """Create an encrypted resume file on disk, yield its path, clean up after."""
    resume_dir = os.path.join(tempfile.gettempdir(), "jobhunter_test_resumes")
    os.makedirs(resume_dir, exist_ok=True)
    plaintext_path = os.path.join(resume_dir, f"{uuid.uuid4().hex}.pdf")

    # Write plaintext, then encrypt (encrypt_and_save removes the plaintext)
    with open(plaintext_path, "wb") as f:
        f.write(sample_resume_bytes)
    enc_path = encrypt_and_save(sample_resume_bytes, plaintext_path)

    yield enc_path

    # Cleanup
    if os.path.exists(enc_path):
        os.remove(enc_path)


class TestResumeCryptoRoundTrip:
    """Verify encrypt → decrypt produces identical bytes."""

    def test_encrypt_decrypt_roundtrip(self, sample_resume_bytes, encrypted_resume_file):
        recovered = decrypt_to_bytes(encrypted_resume_file)
        assert recovered == sample_resume_bytes

    def test_encrypted_file_has_enc_suffix(self, encrypted_resume_file):
        assert encrypted_resume_file.endswith(".pdf.enc")

    def test_plaintext_deleted_after_encrypt(self, encrypted_resume_file):
        plaintext_path = encrypted_resume_file.removesuffix(".enc")
        assert not os.path.exists(plaintext_path)


class TestResumePersistenceFlow:
    """End-to-end: save encrypted bytes to Postgres, delete disk file, recover."""

    def test_save_and_recover(self, sample_resume_bytes, encrypted_resume_file):
        session_id = f"test-{uuid.uuid4().hex[:8]}"

        # 1. Read the encrypted file (what start_session does)
        with open(encrypted_resume_file, "rb") as f:
            encrypted_data = f.read()

        # 2. Save to Postgres
        save_resume(session_id, encrypted_data, ".pdf")

        # 3. Simulate Railway deploy — delete the disk file
        os.remove(encrypted_resume_file)
        assert not os.path.exists(encrypted_resume_file)

        # 4. Recover from Postgres (what serve_resume_file does)
        db_result = get_resume(session_id)
        assert db_result is not None, "Resume not found in Postgres!"

        recovered_encrypted, ext = db_result
        assert ext == ".pdf"
        assert recovered_encrypted == encrypted_data

        # 5. Decrypt the recovered bytes
        recovered_plaintext = _get_fernet().decrypt(recovered_encrypted)
        assert recovered_plaintext == sample_resume_bytes

        # Cleanup
        delete_resume(session_id)

    def test_get_resume_returns_none_for_unknown(self):
        result = get_resume(f"nonexistent-{uuid.uuid4().hex[:8]}")
        assert result is None

    def test_save_resume_upsert(self, encrypted_resume_file):
        """Saving twice with same session_id should update, not fail."""
        session_id = f"test-{uuid.uuid4().hex[:8]}"

        save_resume(session_id, b"first version", ".pdf")
        save_resume(session_id, b"second version", ".pdf")

        result = get_resume(session_id)
        assert result is not None
        assert result[0] == b"second version"

        delete_resume(session_id)

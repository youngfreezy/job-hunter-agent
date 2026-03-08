"""Encrypt / decrypt resume files at rest using Fernet (AES-128-CBC + HMAC).

Key is derived from NEXTAUTH_SECRET via HKDF so we don't need a separate
secret.  Encrypted files are saved with an `.enc` suffix alongside the
original extension (e.g. `abc123.pdf.enc`).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import tempfile
from contextlib import contextmanager
from typing import Generator

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Lazily initialise a Fernet instance keyed from NEXTAUTH_SECRET."""
    global _fernet
    if _fernet is not None:
        return _fernet

    from backend.shared.config import get_settings

    secret = get_settings().NEXTAUTH_SECRET
    if not secret:
        raise RuntimeError("NEXTAUTH_SECRET must be set for resume encryption")

    # Derive a 32-byte key via HKDF then base64-encode for Fernet
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"jobhunter-resume-encryption",
        info=b"resume-at-rest",
    ).derive(secret.encode())

    _fernet = Fernet(base64.urlsafe_b64encode(derived))
    return _fernet


def encrypt_and_save(data: bytes, path: str) -> str:
    """Encrypt *data* and write to *path*.enc.  Returns the encrypted file path."""
    enc_path = path + ".enc"
    token = _get_fernet().encrypt(data)
    with open(enc_path, "wb") as f:
        f.write(token)
    # Remove the plaintext file if it exists
    if os.path.exists(path):
        os.remove(path)
    logger.info("Resume encrypted and saved to %s", enc_path)
    return enc_path


def decrypt_to_bytes(enc_path: str) -> bytes:
    """Read an encrypted file and return the plaintext bytes."""
    with open(enc_path, "rb") as f:
        token = f.read()
    return _get_fernet().decrypt(token)


@contextmanager
def decrypted_tempfile(enc_path: str) -> Generator[str, None, None]:
    """Context manager: decrypt to a temp file, yield its path, then delete it.

    Usage::

        with decrypted_tempfile("/tmp/jobhunter_resumes/abc.pdf.enc") as path:
            await file_input.set_input_files(path)
        # temp file is deleted here
    """
    data = decrypt_to_bytes(enc_path)

    # Recover the original extension (strip .enc)
    base = enc_path.removesuffix(".enc")
    ext = os.path.splitext(base)[1]  # e.g. ".pdf"

    fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="jh_resume_")
    try:
        os.write(fd, data)
        os.close(fd)
        yield tmp_path
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

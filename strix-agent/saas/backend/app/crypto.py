"""Symmetric encryption for real integration credentials at rest.

Fernet requires a 32-byte urlsafe-base64 key; `settings.credentials_encryption_key`
can be any string — it's hashed into a valid Fernet key so operators don't
need to hand-generate one, while still getting real authenticated
encryption (AES-128-CBC + HMAC-SHA256). Change the setting for any
non-local deployment, same as `SAAS_SESSION_SECRET`.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from .settings import settings


def _fernet() -> Fernet:
    key = hashlib.sha256(settings.credentials_encryption_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()


def decrypt_or_legacy_plaintext(value: str | None) -> str | None:
    """Decrypt a Fernet value, tolerating legacy plaintext rows."""
    if not value:
        return None
    try:
        return decrypt(value)
    except InvalidToken:
        return value

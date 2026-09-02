"""Field-level encryption for sensitive SQLAlchemy columns.

Uses the same Fernet master key as ``CredentialVault`` (see
``credential_vault.py``) so there is exactly one material to derive from. The
master key material is memoized per ``CREDENTIAL_MASTER_KEY`` value and re-
derived automatically if the environment key changes (tests rotate it).

Two rules keep this safe to use anywhere:
  1. Encryption is TRANSPARENT at the ORM layer — the Python attribute stays a
     ``str``; only the bytes at rest change. Existing queries that read/write
     the attribute keep working unchanged.
  2. Reads fail OPEN for pre-encryption plaintext rows (legacy migration data)
     so hot-fix code paths never crash; migration ``ff06`` re-encrypts them.
"""
from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator

# CredentialVault is imported lazily: app.services is a heavy package whose
# __init__ imports the entire service tree (including modules that import
# app.database). Importing it at module load would create a circular import
# during app.database init.


_DEV_KEY = "dev-master-key-replace-in-production-32chars"  # keep in sync with CredentialVault.DEV_FALLBACK_KEY

_cache: dict = {"key": None, "fernet": None}


def _load_vault() -> "CredentialVault":
    from app.services.credential_vault import CredentialVault
    return CredentialVault()


def get_fernet() -> Fernet:
    """Return the Fernet derived from the current master key (memoized)."""
    env_key = os.environ.get("CREDENTIAL_MASTER_KEY", "") or _DEV_KEY
    if _cache["key"] != env_key:
        _cache["key"] = env_key
        _cache["fernet"] = _load_vault()._fernet
    return _cache["fernet"]


def is_fernet_token(value: bytes | bytearray | memoryview) -> bool:
    """Best-effort detection: ``True`` when the bytes decrypt with the master key."""
    try:
        get_fernet().decrypt(bytes(value))
        return True
    except Exception:
        return False


class EncryptedText(TypeDecorator):
    """String column encrypted at rest; transparent ``str`` semantics in Python.

    ``process_result_value`` degrades gracefully: legacy plaintext rows decrypt
    to themselves so a partially-migrated database keeps working.
    """

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return get_fernet().encrypt(str(value).encode("utf-8"))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return get_fernet().decrypt(value).decode("utf-8")
        except InvalidToken:
            return bytes(value).decode("utf-8", errors="replace")
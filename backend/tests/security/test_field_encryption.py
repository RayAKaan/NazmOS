"""Phase C: field-level encryption is transparent to the ORM and opaque at rest."""
import asyncio

from cryptography.fernet import Fernet

from app.database.encryption import EncryptedText, get_fernet, is_fernet_token
from app.database.models import User


def test_encrypted_text_round_trips():
    col = EncryptedText()
    secret = "JBSWY3DPEHPK3PXP"
    bound = col.process_bind_param(secret, None)
    assert bound is not None
    assert secret not in str(bound)  # never stored as plaintext
    assert is_fernet_token(bound) is True
    assert col.process_result_value(bound, None) == secret


def test_encrypted_text_handles_none():
    col = EncryptedText()
    assert col.process_bind_param(None, None) is None
    assert col.process_result_value(None, None) is None


def test_encrypted_text_reads_legacy_plaintext_without_crash():
    col = EncryptedText()
    legacy = b"legacy-plaintext-not-encrypted"
    assert is_fernet_token(legacy) is False
    assert col.process_result_value(legacy, None) == legacy.decode("utf-8", errors="replace")


def test_master_fernet_is_memoized_per_key():
    fernet_a = get_fernet()
    fernet_b = get_fernet()
    assert fernet_a == fernet_b
    assert isinstance(fernet_a, Fernet)


def test_user_model_two_factor_secret_column_encrypted():
    assert isinstance(User.__table__.c.two_factor_secret.type, EncryptedText)


def test_user_write_read_transparent(monkeypatch):
    # Model-level: writing the str attribute stores ciphertext bytes in the DB
    # column raw value; reading via the ORM returns the original str.
    secret = "BASE32SECRETVALUE123456"
    typed = User.__table__.c.two_factor_secret.type
    raw = typed.process_bind_param(secret, None)
    assert raw != secret
    assert is_fernet_token(raw) is True
    assert typed.process_result_value(raw, None) == secret
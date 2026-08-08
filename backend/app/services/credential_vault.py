from typing import Optional, Any
import base64
import json
from dataclasses import dataclass
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import os
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class EncryptedCredential:
    ciphertext: str
    encrypted_dek: str
    version: str


class CredentialVault:
    VERSION = "v1"
    SALT = b"nazmos_vault_salt_v3"
    ITERATIONS = 100000
    DEV_FALLBACK_KEY = "dev-master-key-replace-in-production-32chars"

    def __init__(self, master_key: Optional[str] = None):
        from app.config import get_settings

        env_key = os.environ.get("CREDENTIAL_MASTER_KEY", "")
        effective_key = master_key or env_key or None

        if effective_key is None:
            if get_settings().ENVIRONMENT == "production":
                raise RuntimeError(
                    "FATAL: CREDENTIAL_MASTER_KEY is required in production and must be >= 32 chars. "
                    "It encrypts POS and integration credentials. Set CREDENTIAL_MASTER_KEY before "
                    "instantiating CredentialVault."
                )
            # In development we allow a known dev key only for local testing.
            effective_key = "dev-master-key-replace-in-production-32chars"
            logger.warning(
                "credential_master_key_not_set",
                extra={"detail": "CREDENTIAL_MASTER_KEY is not set. Using dev-only key. "
                        "Set CREDENTIAL_MASTER_KEY before production."},
            )

        self._master_key = effective_key.encode()
        self._fernet = self._create_fernet(self._master_key)

    def _create_fernet(self, key: bytes) -> Fernet:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.SALT,
            iterations=self.ITERATIONS,
        )
        derived_key = base64.urlsafe_b64encode(kdf.derive(key))
        return Fernet(derived_key)

    def _generate_dek(self) -> bytes:
        return Fernet.generate_key()

    def encrypt(self, plaintext: dict) -> EncryptedCredential:
        plaintext_json = json.dumps(plaintext)
        
        dek = self._generate_dek()
        dek_fernet = Fernet(dek)
        ciphertext = dek_fernet.encrypt(plaintext_json.encode())
        
        encrypted_dek = self._fernet.encrypt(dek)
        
        return EncryptedCredential(
            ciphertext=base64.b64encode(ciphertext).decode(),
            encrypted_dek=base64.b64encode(encrypted_dek).decode(),
            version=self.VERSION,
        )

    def decrypt(self, encrypted: EncryptedCredential) -> dict:
        if encrypted.version != self.VERSION:
            logger.warning(
                "credential_version_mismatch",
                expected=self.VERSION,
                actual=encrypted.version,
            )
        
        encrypted_dek = base64.b64decode(encrypted.encrypted_dek)
        dek = self._fernet.decrypt(encrypted_dek)
        
        dek_fernet = Fernet(dek)
        ciphertext = base64.b64decode(encrypted.ciphertext)
        plaintext = dek_fernet.decrypt(ciphertext)
        
        return json.loads(plaintext.decode())

    def encrypt_to_bytes(self, plaintext: dict) -> bytes:
        encrypted = self.encrypt(plaintext)
        return json.dumps({
            "ciphertext": encrypted.ciphertext,
            "encrypted_dek": encrypted.encrypted_dek,
            "version": encrypted.version,
        }).encode()

    def decrypt_from_bytes(self, data: bytes) -> dict:
        parsed = json.loads(data.decode())
        return self.decrypt(EncryptedCredential(
            ciphertext=parsed["ciphertext"],
            encrypted_dek=parsed["encrypted_dek"],
            version=parsed["version"],
        ))


class POSCredentialManager:
    def __init__(self, vault: Optional[CredentialVault] = None):
        self.vault = vault or CredentialVault()

    def encrypt_credentials(self, adapter_type: str, credentials: dict) -> bytes:
        full_credentials = {
            "adapter_type": adapter_type,
            "credentials": credentials,
        }
        return self.vault.encrypt_to_bytes(full_credentials)

    def decrypt_credentials(self, encrypted_data: bytes) -> dict:
        return self.vault.decrypt_from_bytes(encrypted_data)

    def validate_tally_credentials(self, credentials: dict) -> bool:
        required = ["company_name", "tally_url"]
        return all(key in credentials for key in required)

    def validate_shopify_credentials(self, credentials: dict) -> bool:
        required = ["shop_name", "access_token", "api_version"]
        return all(key in credentials for key in required)

    def validate_woocommerce_credentials(self, credentials: dict) -> bool:
        required = ["site_url", "consumer_key", "consumer_secret"]
        return all(key in credentials for key in required)

    def validate_zoho_credentials(self, credentials: dict) -> bool:
        required = ["organization_id", "client_id", "client_secret", "refresh_token"]
        return all(key in credentials for key in required)

    def validate_credentials(self, adapter_type: str, credentials: dict) -> bool:
        validators = {
            "tally": self.validate_tally_credentials,
            "shopify": self.validate_shopify_credentials,
            "woocommerce": self.validate_woocommerce_credentials,
            "zoho": self.validate_zoho_credentials,
            "csv_webhook": lambda c: True,
            "custom_api": lambda c: "base_url" in c or "api_key" in c,
            "foodics": lambda c: bool(c.get("webhook_secret")),
            "salla": lambda c: bool(c.get("access_token") or c.get("webhook_secret")),
            "zid": lambda c: bool(c.get("access_token")),
            "qoyod": lambda c: bool(c.get("api_key")),
        }
        
        validator = validators.get(adapter_type)
        if not validator:
            logger.error("unknown_adapter_type", adapter_type=adapter_type)
            return False
        
        return validator(credentials)

"""OAuth initiation and callback manager for POS / e-commerce integrations.

Stores short-lived state in memory (Redis-backed in production). Exchanges the
authorization code for an access token and persists credentials in POSConnection.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.credential_vault import POSCredentialManager

settings = get_settings()

_OAUTH_PROVIDERS: dict[str, dict[str, Any]] = {
    "salla": {
        "auth_url": "https://accounts.salla.sa/oauth2/auth",
        "token_url": "https://accounts.salla.sa/oauth2/token",
        "scopes": "products.read orders.read inventory.read",
    },
    "zid": {
        "auth_url": "https://oauth.zid.sa/authorize",
        "token_url": "https://oauth.zid.sa/token",
        "scopes": "products.read orders.read",
    },
    "foodics": {
        "auth_url": "https://console.foodics.com/oauth/authorize",
        "token_url": "https://console.foodics.com/oauth/token",
        "scopes": "read",
    },
}

# In-memory state store. Production should use Redis with TTL.
_STATE_STORE: dict[str, dict[str, Any]] = {}


def _state_key(state: str) -> str:
    return f"oauth_state:{state}"


def _get_client_config(provider: str) -> tuple[str | None, str | None]:
    prefix = provider.upper()
    client_id = getattr(settings, f"{prefix}_CLIENT_ID", None) or getattr(settings, f"{provider}_client_id", None)
    client_secret = getattr(settings, f"{prefix}_CLIENT_SECRET", None) or getattr(settings, f"{provider}_client_secret", None)
    return client_id, client_secret


def build_authorize_url(
    provider: str,
    business_id: str | UUID,
    redirect_uri: str,
) -> dict[str, Any]:
    config = _OAUTH_PROVIDERS.get(provider)
    if not config:
        raise ValueError(f"Unsupported OAuth provider: {provider}")

    client_id, _ = _get_client_config(provider)
    if not client_id:
        raise ValueError(f"Missing client_id for {provider}; set {provider.upper()}_CLIENT_ID")

    state = secrets.token_urlsafe(24)
    _STATE_STORE[_state_key(state)] = {
        "provider": provider,
        "business_id": str(business_id),
        "redirect_uri": redirect_uri,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
    }

    url = (
        f"{config['auth_url']}"
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={config['scopes'].replace(' ', '%20')}"
        f"&state={state}"
    )
    return {"authorization_url": url, "state": state, "provider": provider}


async def exchange_code(
    provider: str,
    code: str,
    state: str,
    redirect_uri: str,
) -> dict[str, Any]:
    config = _OAUTH_PROVIDERS.get(provider)
    if not config:
        raise ValueError(f"Unsupported OAuth provider: {provider}")

    stored = _STATE_STORE.pop(_state_key(state), None)
    if not stored:
        raise ValueError("Invalid or expired OAuth state")
    if stored.get("expires_at", datetime.min.replace(tzinfo=timezone.utc)) < datetime.now(timezone.utc):
        raise ValueError("OAuth state expired")
    if stored.get("provider") != provider:
        raise ValueError("OAuth provider mismatch")

    client_id, client_secret = _get_client_config(provider)
    if not client_id or not client_secret:
        raise ValueError(f"Missing OAuth credentials for {provider}")

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            config["token_url"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Accept": "application/json"},
        )

    if response.status_code != 200:
        raise ValueError(f"Token exchange failed: {response.status_code} {response.text}")

    token_data = response.json()
    return {
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token"),
        "expires_in": token_data.get("expires_in"),
        "token_type": token_data.get("token_type", "Bearer"),
        "business_id": stored["business_id"],
    }


async def save_oauth_credentials(
    db: AsyncSession,
    provider: str,
    business_id: str | UUID,
    token_data: dict[str, Any],
    connection_name: str | None = None,
) -> dict[str, Any]:
    vault = POSCredentialManager()
    credentials = {
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token"),
        "token_type": token_data.get("token_type", "Bearer"),
    }
    encrypted = vault.encrypt_credentials(provider, credentials)

    res = await db.execute(text("""
        INSERT INTO pos_connections
            (id, business_id, adapter_type, connection_name, credentials_encrypted,
             sync_status, is_active, created_at, updated_at)
        VALUES
            (gen_random_uuid(), :business_id, :provider, :name, :creds,
             'never_synced', true, NOW(), NOW())
        RETURNING id
    """), {
        "business_id": str(business_id),
        "provider": provider,
        "name": connection_name or f"{provider.title()} OAuth",
        "creds": encrypted,
    })
    await db.commit()
    row = res.fetchone()
    return {"ok": True, "connection_id": str(row.id), "provider": provider}

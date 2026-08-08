"""Unit tests for OAuth manager."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from app.services.oauth_manager import build_authorize_url, exchange_code, save_oauth_credentials


def test_build_authorize_url_requires_client_id(monkeypatch):
    with patch("app.services.oauth_manager._get_client_config", return_value=(None, None)):
        with pytest.raises(ValueError):
            build_authorize_url("salla", uuid4(), "https://app.nazm.ai/callback")


def test_build_authorize_url_success(monkeypatch):
    with patch("app.services.oauth_manager._get_client_config", return_value=("client_123", "secret")):
        result = build_authorize_url("salla", uuid4(), "https://app.nazm.ai/callback")
    assert "authorization_url" in result
    assert result["provider"] == "salla"
    assert "client_123" in result["authorization_url"]


@pytest.mark.asyncio
async def test_exchange_code_success():
    business_id = uuid4()
    with patch("app.services.oauth_manager._get_client_config", return_value=("client", "secret")):
        auth = build_authorize_url("salla", business_id, "https://app.nazm.ai/callback")
        state = auth["state"]

    response = MagicMock()
    response.status_code = 200
    response.json = MagicMock(return_value={"access_token": "tok", "refresh_token": "ref", "expires_in": 3600})
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)
    fake_client.post = AsyncMock(return_value=response)
    with patch("app.services.oauth_manager._get_client_config", return_value=("client", "secret")), \
         patch("httpx.AsyncClient", return_value=fake_client):
        result = await exchange_code("salla", "authcode", state, "https://app.nazm.ai/callback")
    assert result["access_token"] == "tok"
    assert result["business_id"] == str(business_id)


@pytest.mark.asyncio
async def test_exchange_code_invalid_state():
    with pytest.raises(ValueError):
        await exchange_code("salla", "code", "invalid", "https://app.nazm.ai/callback")


@pytest.mark.asyncio
async def test_save_oauth_credentials():
    db = MagicMock()
    inserted_id = uuid4()
    db.execute = AsyncMock(return_value=MagicMock(fetchone=MagicMock(return_value=MagicMock(id=inserted_id))))
    db.commit = AsyncMock()
    result = await save_oauth_credentials(db, "salla", uuid4(), {"access_token": "tok"})
    assert result["ok"] is True
    assert result["connection_id"] == str(inserted_id)

"""Unit tests for infrastructure probes (Redis + Temporal substrate)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.infra_service import ping_redis, ping_temporal


@pytest.mark.asyncio
async def test_ping_redis_without_url():
    result = await ping_redis("")
    assert result["reachable"] is False


@pytest.mark.asyncio
async def test_ping_redis_success():
    fake_client = MagicMock()
    fake_client.ping = AsyncMock(return_value=None)
    fake_client.info = AsyncMock(return_value={"redis_version": "7.0"})
    fake_client.aclose = AsyncMock(return_value=None)
    with patch("redis.asyncio.from_url", return_value=fake_client):
        result = await ping_redis("redis://localhost")
    assert result["reachable"] is True
    assert result["version"] == "7.0"


@pytest.mark.asyncio
async def test_ping_temporal_disabled():
    with patch("app.services.infra_service.settings.USE_TEMPORAL", False):
        result = await ping_temporal()
    assert result["enabled"] is False
    assert result["reachable"] is False


@pytest.mark.asyncio
async def test_ping_temporal_reachable():
    fake = MagicMock()
    fake.workflow_service.get_system_info = AsyncMock(
        return_value=MagicMock(server_version="1.27.0")
    )
    with (
        patch("app.services.infra_service.settings.USE_TEMPORAL", True),
        patch("temporalio.client.Client.connect", new=AsyncMock(return_value=fake)),
    ):
        result = await ping_temporal()
    assert result["enabled"] is True
    assert result["reachable"] is True
    assert result["server_version"] == "1.27.0"
    assert result["namespace"] == "default"


@pytest.mark.asyncio
async def test_ping_temporal_unreachable():
    with (
        patch("app.services.infra_service.settings.USE_TEMPORAL", True),
        patch(
            "temporalio.client.Client.connect",
            new=AsyncMock(side_effect=RuntimeError("connect refused")),
        ),
    ):
        result = await ping_temporal()
    assert result["enabled"] is True
    assert result["reachable"] is False
    assert "reason" in result
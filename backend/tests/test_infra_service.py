"""Unit tests for infrastructure probes."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.services.infra_service import ping_redis, ping_celery, get_celery_queue_lengths


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


def test_ping_celery_disabled():
    with patch("app.services.infra_service.settings.USE_CELERY", False):
        result = ping_celery()
    assert result["enabled"] is False


def test_get_celery_queue_lengths_disabled():
    with patch("app.services.infra_service.settings.USE_CELERY", False):
        result = get_celery_queue_lengths()
    assert result["enabled"] is False

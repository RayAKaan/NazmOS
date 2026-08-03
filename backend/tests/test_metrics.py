"""Test Prometheus metrics exposure."""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_format():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/metrics")
    assert response.status_code == 200
    assert "python_info" in response.text
    assert "nazmos_http_requests_total" in response.text

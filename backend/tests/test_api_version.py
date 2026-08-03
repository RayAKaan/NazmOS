"""Test API version header propagation."""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.middleware.api_version import API_VERSION, API_VERSION_HEADER


@pytest.mark.asyncio
async def test_api_version_header_on_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    assert response.headers[API_VERSION_HEADER] == API_VERSION

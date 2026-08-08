"""Test Prometheus metrics exposure."""
import uuid

import pytest
from httpx import AsyncClient, ASGITransport

import app.main as main_module
from app.main import app


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_format():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/metrics")
    assert response.status_code == 200
    assert "python_info" in response.text
    assert "nazmos_http_requests_total" in response.text


@pytest.mark.asyncio
async def test_metrics_requires_token_when_configured():
    previous = main_module.settings.METRICS_TOKEN
    main_module.settings.METRICS_TOKEN = "supersecret"
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/metrics")
            assert response.status_code == 401

            response = await ac.get("/metrics", headers={"X-Metrics-Token": "wrong"})
            assert response.status_code == 401

            response = await ac.get("/metrics", headers={"X-Metrics-Token": "supersecret"})
            assert response.status_code == 200
    finally:
        main_module.settings.METRICS_TOKEN = previous


@pytest.mark.asyncio
async def test_metric_path_uses_route_template_not_concrete_uuid():
    item_id = str(uuid.uuid4())
    concrete_path = f"/api/v1/inventory/{item_id}/detail"
    template_path = "/api/v1/inventory/{item_id}/detail"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Unauthenticated request still matches routing and is recorded.
        response = await ac.get(concrete_path)
        assert response.status_code == 401

        metrics = (await ac.get("/metrics")).text

    assert f'path="{template_path}"' in metrics
    assert f'path="{concrete_path}"' not in metrics

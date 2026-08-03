import pytest

from app.adapters.registry import (
    ADAPTER_REGISTRY,
    FoodicsWebhookAdapter,
    SallaWebhookAdapter,
    CustomAPIAdapter,
    CSVWebhookAdapter,
)


def test_registry_includes_webhook_adapters():
    assert "foodics" in ADAPTER_REGISTRY
    assert "salla" in ADAPTER_REGISTRY


@pytest.mark.asyncio
async def test_foodics_adapter_test_connection_with_secret():
    adapter = FoodicsWebhookAdapter({
        "adapter_type": "foodics",
        "credentials": {"webhook_secret": "super-secret"},
    })
    assert await adapter.test_connection() is True


@pytest.mark.asyncio
async def test_foodics_adapter_test_connection_without_secret():
    adapter = FoodicsWebhookAdapter({
        "adapter_type": "foodics",
        "credentials": {},
    })
    assert await adapter.test_connection() is False


@pytest.mark.asyncio
async def test_salla_adapter_test_connection_with_secret():
    adapter = SallaWebhookAdapter({
        "adapter_type": "salla",
        "credentials": {"webhook_secret": "super-secret"},
    })
    assert await adapter.test_connection() is True


@pytest.mark.asyncio
async def test_salla_adapter_test_connection_without_secret():
    adapter = SallaWebhookAdapter({
        "adapter_type": "salla",
        "credentials": {},
    })
    assert await adapter.test_connection() is False


@pytest.mark.asyncio
async def test_custom_api_adapter_test_connection_without_url():
    adapter = CustomAPIAdapter({
        "adapter_type": "custom_api",
        "credentials": {"api_key": "key"},
    })
    assert await adapter.test_connection() is False


@pytest.mark.asyncio
async def test_csv_webhook_adapter_test_connection_without_endpoint():
    adapter = CSVWebhookAdapter({
        "adapter_type": "csv_webhook",
        "credentials": {},
    })
    assert await adapter.test_connection() is False

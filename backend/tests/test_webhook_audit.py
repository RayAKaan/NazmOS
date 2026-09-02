"""Webhook audit, deduplication, signature verification, and replay tests.

These tests require a Postgres test database and are skipped automatically
when it is unavailable.
"""
import json
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.config import get_settings
from app.services import webhook_audit_service

pytestmark = pytest.mark.asyncio


def _async_result(value: dict):
    from unittest.mock import AsyncMock

    return AsyncMock(return_value=value)()


def _foodics_payload(external_id: str):
    return json.dumps({"event": "order.created", "order": {"id": external_id}}).encode("utf-8")


async def test_foodics_webhook_requires_authentication(client: AsyncClient):
    response = await client.post(
        f"/api/v1/pos/foodics/webhook?business_id={uuid4()}",
        headers={"x-foodics-signature": "invalid-signature"},
        content=b"{}",
    )
    assert response.status_code == 401


async def test_webhook_rejected_when_business_not_registered_for_provider(
    authenticated_client: dict, monkeypatch, db_session
):
    """Phase B: a business_id alone must never authorize a webhook target.

    Without an active POSConnection for the claimed provider the webhook is
    rejected (401) even with a valid signature token.
    """
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]

    settings = get_settings()
    monkeypatch.setattr(settings, "FOODICS_WEBHOOK_TOKEN", "test-webhook-token")

    from app.database.models import POSConnection

    # No POSConnection for the business -> registration check fails.
    url = f"/api/v1/pos/foodics/webhook?business_id={ctx['business_id']}"
    headers = {"x-webhook-token": "test-webhook-token"}
    response = await client.post(url, headers=headers, content=_foodics_payload("evt-unregistered"))
    assert response.status_code == 401, response.text


async def test_foodics_webhook_dedupes_by_external_event_id(
    authenticated_client: dict, monkeypatch, db_session
):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    from app.database.models import POSConnection

    # Phase B contract: the target business must be registered with an active
    # POS connection for the provider before webhooks are honored.
    connection = POSConnection(
        business_id=business_id,
        adapter_type="foodics",
        connection_name="Foodics Test",
        credentials_encrypted=b"test-creds",
        is_active=True,
    )
    db_session.add(connection)
    await db_session.commit()

    settings = get_settings()
    monkeypatch.setattr(settings, "FOODICS_WEBHOOK_TOKEN", "test-webhook-token")
    monkeypatch.setattr(
        "app.routers.pos_webhooks._process_webhook",
        lambda provider, payload, bid, db: _async_result({"processed": True, "provider": provider}),
    )

    external_id = f"evt-{uuid4().hex[:8]}"
    url = f"/api/v1/pos/foodics/webhook?business_id={business_id}"
    headers = {"x-webhook-token": "test-webhook-token"}

    first = await client.post(url, headers=headers, content=_foodics_payload(external_id))
    assert first.status_code == 200, first.text

    second = await client.post(url, headers=headers, content=_foodics_payload(external_id))
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "already_processed"


async def test_webhook_replay_requires_platform_operator(
    authenticated_client: dict, monkeypatch, db_session
):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    monkeypatch.setattr(
        "app.routers.pos_webhooks._process_webhook",
        lambda provider, payload, bid, db: _async_result({"replayed": True}),
    )

    event = await webhook_audit_service.record_webhook_event(
        session=db_session,
        business_id=business_id,
        provider="foodics",
        payload=b'{"event":"order.created","order":{"id":"replay-1"}}',
        signature_valid=True,
        event_type="order.created",
        external_event_id="replay-1",
    )

    # A merchant owner is not a platform operator: replay is denied (403).
    denied = await client.post(
        f"/api/v1/pos/admin/webhooks/{event.id}/replay",
        headers=ctx["headers"],
    )
    assert denied.status_code == 403, denied.text

    # Platform operator identity may replay the webhook.
    monkeypatch.setattr(
        "app.middleware.business_access.is_platform_operator", lambda user: True
    )
    response = await client.post(
        f"/api/v1/pos/admin/webhooks/{event.id}/replay",
        headers=ctx["headers"],
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "replayed"
    assert data["result"]["replayed"] is True

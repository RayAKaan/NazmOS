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


def _foodics_payload(external_id: str):
    return json.dumps({"event": "order.created", "order": {"id": external_id}}).encode("utf-8")


async def test_foodics_webhook_requires_authentication(client: AsyncClient):
    response = await client.post(
        f"/api/v1/pos/foodics/webhook?business_id={uuid4()}",
        headers={"x-foodics-signature": "invalid-signature"},
        content=b"{}",
    )
    assert response.status_code == 401


async def test_foodics_webhook_dedupes_by_external_event_id(
    authenticated_client: dict, monkeypatch, db_session
):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    settings = get_settings()
    monkeypatch.setattr(settings, "FOODICS_WEBHOOK_TOKEN", "test-webhook-token")
    monkeypatch.setattr(
        "app.routers.pos_webhooks._process_webhook",
        lambda provider, payload, bid, db: {"processed": True, "provider": provider},
    )

    external_id = f"evt-{uuid4().hex[:8]}"
    url = f"/api/v1/pos/foodics/webhook?business_id={business_id}"
    headers = {"x-webhook-token": "test-webhook-token"}

    first = await client.post(url, headers=headers, content=_foodics_payload(external_id))
    assert first.status_code == 200, first.text

    second = await client.post(url, headers=headers, content=_foodics_payload(external_id))
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "already_processed"


async def test_webhook_replay_requires_admin_or_owner(
    authenticated_client: dict, monkeypatch, db_session
):
    ctx = authenticated_client
    client: AsyncClient = ctx["client"]
    business_id = ctx["business_id"]

    monkeypatch.setattr(
        "app.routers.pos_webhooks._process_webhook",
        lambda provider, payload, bid, db: {"replayed": True},
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

    response = await client.post(
        f"/api/v1/pos/admin/webhooks/{event.id}/replay",
        headers=ctx["headers"],
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "replayed"
    assert data["result"]["replayed"] is True

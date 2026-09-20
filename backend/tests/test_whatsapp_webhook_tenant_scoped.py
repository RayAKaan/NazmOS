"""WhatsApp webhook approve/reject must be tenant-scoped and truthful.

Regression for FIX-6: the unauthenticated webhook previously called
``run_agent_approval``/``run_agent_rejection`` with no ``business_id``, so under
Postgres RLS every agent_actions row was invisible (the app assumes the
restricted role with no tenant) — the guarded UPDATE no-oped while the reply
still claimed "✅ Approved".  Button ids now carry the tenant
(``{prefix}_{business_id}_{action_id}``) and the receiver:

1. parses + validates the tenant from the button id,
2. scopes the request session to that tenant (RLS + ``business_id`` WHERE),
3. only sends the confirmed/denied messages when the operation actually succeeded.
"""
import hashlib
import hmac
import json
import types
import uuid

import pytest
from sqlalchemy import text

WHATSAPP_SECRET = "test-webhook-secret"


def _button_payload(button_id: str) -> bytes:
    body = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "+966500000000",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button",
                                        "button_reply": {"id": button_id},
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    return json.dumps(body).encode()


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(WHATSAPP_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _headers(body: bytes) -> dict:
    return {"x-hub-signature-256": _sign(body)}


async def _seed_pending_action(db, action_type: str = "restock"):
    business_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    item_id = str(uuid.uuid4())
    action_id = str(uuid.uuid4())

    await db.execute(
        text("""
            INSERT INTO users (id, email, password_hash, full_name, role, is_active)
            VALUES (:id, :email, 'hash', 'Owner', 'owner', true)
        """),
        {"id": user_id, "email": f"wa_owner_{uuid.uuid4().hex[:8]}@example.com"},
    )
    await db.execute(
        text(
            "INSERT INTO businesses (id, name, type, currency, owner_id) "
            "VALUES (:id, 'WA Test', 'retail', 'SAR', :owner_id)"
        ),
        {"id": business_id, "owner_id": user_id},
    )
    await db.execute(
        text("""
            INSERT INTO items (id, business_id, name, sku, unit, cost_price, sell_price, is_active)
            VALUES (:id, :business_id, 'Widget', 'W-001', 'piece', 10, 20, true)
        """),
        {"id": item_id, "business_id": business_id},
    )
    await db.execute(
        text("""
            INSERT INTO agent_actions
                (id, business_id, action_type, status, confidence, priority, title, summary,
                 payload, autonomy_dial_at_creation, estimated_value_sar)
            VALUES
                (:id, :business_id, :action_type, 'pending_approval', 0.9, 1, 'Approve Widget',
                 'Need more widgets', CAST(:payload AS JSON), 50, 100)
        """),
        {
            "id": action_id,
            "business_id": business_id,
            "action_type": action_type,
            "payload": f'{{"item_id": "{item_id}", "recommended_qty": 15}}',
        },
    )
    await db.commit()
    return business_id, item_id, action_id


async def _status(db, action_id: str) -> str | None:
    row = (await db.execute(
        text("SELECT status FROM agent_actions WHERE id = :id"), {"id": action_id}
    )).fetchone()
    return row.status if row else None


@pytest.fixture
def _sent(monkeypatch):
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.routers.whatsapp.settings",
        types.SimpleNamespace(WHATSAPP_APP_SECRET=WHATSAPP_SECRET),
    )

    async def fake_send(to_number: str, text: str):
        sent.append((to_number, text))

    monkeypatch.setattr("app.routers.whatsapp.send_notification", fake_send)
    return sent


@pytest.mark.asyncio
async def test_approve_scopes_to_button_business_and_executes(client, db_session, _sent):
    bid, _item, aid = await _seed_pending_action(db_session)
    body = _button_payload(f"approve_{bid}_{aid}")
    r = await client.post("/api/v1/whatsapp/webhook", content=body, headers=_headers(body))

    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert await _status(db_session, aid) == "executed", "approval must actually transition the row"
    texts = [t for _, t in _sent]
    assert any(not t.startswith("⚠️") for t in texts), f"expected an approval confirmation, got {texts}"
    assert any(t.startswith("✅") for t in texts), f"expected confirmed text, got {texts}"


@pytest.mark.asyncio
async def test_approve_wrong_tenant_button_fails_closed(client, db_session, _sent):
    bid, _item, aid = await _seed_pending_action(db_session)
    wrong_business = str(uuid.uuid4())
    body = _button_payload(f"approve_{wrong_business}_{aid}")
    r = await client.post("/api/v1/whatsapp/webhook", content=body, headers=_headers(body))

    assert r.status_code == 200
    assert await _status(db_session, aid) == "pending_approval", \
        "an action must never be approved via a button holding another tenant's id"
    texts = [m for _, m in _sent]
    assert any(t.startswith("⚠️") for t in texts), \
        f"failure must be reported (not a false approval), got {_sent}"


@pytest.mark.asyncio
async def test_reject_scopes_to_button_business(client, db_session, _sent):
    bid, _item, aid = await _seed_pending_action(db_session)
    body = _button_payload(f"reject_{bid}_{aid}")
    r = await client.post("/api/v1/whatsapp/webhook", content=body, headers=_headers(body))

    assert r.status_code == 200
    assert await _status(db_session, aid) == "rejected"
    texts = [m for _, m in _sent]
    assert any(t.startswith("❌") for t in texts), f"expected rejection confirmation, got {_sent}"


@pytest.mark.asyncio
async def test_approve_non_pending_action_reports_failure(client, db_session, _sent):
    bid, _item, aid = await _seed_pending_action(db_session)
    first = _button_payload(f"approve_{bid}_{aid}")
    r1 = await client.post("/api/v1/whatsapp/webhook", content=first, headers=_headers(first))
    assert r1.status_code == 200
    assert await _status(db_session, aid) == "executed"

    # Second tap: already executed -> must NOT claim "Approved".
    r2 = await client.post("/api/v1/whatsapp/webhook", content=first, headers=_headers(first))
    assert r2.status_code == 200
    texts = [m for _, m in _sent]
    assert any(t.startswith("⚠️") for t in texts), \
        f"re-tap must report it did not approve, got {_sent}"


@pytest.mark.asyncio
async def test_unresolvable_legacy_button_not_approved(client, db_session, _sent):
    bid, _item, aid = await _seed_pending_action(db_session)
    # Legacy id without the tenant component cannot be routed.
    legacy = _button_payload(f"approve_{aid}")
    r = await client.post("/api/v1/whatsapp/webhook", content=legacy, headers=_headers(legacy))
    assert r.status_code == 200
    assert await _status(db_session, aid) == "pending_approval"
    texts = [m for _, m in _sent]
    assert any("could not be located" in t for t in texts), f"got {_sent}"


@pytest.mark.asyncio
async def test_webhook_requires_hmac(client, db_session, _sent):
    bid, _item, aid = await _seed_pending_action(db_session)
    body = _button_payload(f"approve_{bid}_{aid}")
    r = await client.post("/api/v1/whatsapp/webhook", content=body, headers={"x-hub-signature-256": "sha256=bad"})
    assert r.status_code == 401, "an invalid signature must fail before any business logic runs"
    assert await _status(db_session, aid) == "pending_approval"
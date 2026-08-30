"""Tests for Nazm Agent action approval and outcome tracking."""
import uuid

import pytest
from sqlalchemy import text

from app.services.agent_action_executor import approve_agent_action


@pytest.mark.asyncio
async def test_approve_restock_action_writes_outcome(db_session):
    business_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    item_id = str(uuid.uuid4())
    action_id = str(uuid.uuid4())

    await db_session.execute(
        text("""
            INSERT INTO users (id, email, password_hash, full_name, role, is_active)
            VALUES (:id, :email, 'hash', 'Owner', 'owner', true)
        """),
        {"id": user_id, "email": f"agent_owner_{uuid.uuid4().hex[:8]}@example.com"},
    )
    await db_session.execute(
        text("INSERT INTO businesses (id, name, type, currency) VALUES (:id, 'Agent Test', 'retail', 'SAR')"),
        {"id": business_id},
    )
    await db_session.execute(
        text("""
            INSERT INTO items (id, business_id, name, sku, unit, cost_price, sell_price, is_active)
            VALUES (:id, :business_id, 'Widget', 'W-001', 'piece', 10, 20, true)
        """),
        {"id": item_id, "business_id": business_id},
    )
    await db_session.execute(
        text("""
            INSERT INTO agent_actions
                (id, business_id, action_type, status, confidence, priority, title, summary,
                 payload, autonomy_dial_at_creation, estimated_value_sar)
            VALUES
                (:id, :business_id, 'restock', 'pending_approval', 0.9, 1, 'Restock Widget',
                 'Need more widgets', CAST(:payload AS JSON), 50, 100)
        """),
        {
            "id": action_id,
            "business_id": business_id,
            "payload": f'{{"item_id": "{item_id}", "recommended_qty": 15}}',
        },
    )
    await db_session.commit()

    result = await approve_agent_action(db_session, action_id, note="Approved in test", decided_by=user_id)

    assert result["ok"] is True
    assert result["outcome"]["executed"] is True
    assert result["outcome"]["action"] == "purchase_order_created"

    row = await db_session.execute(
        text("SELECT status, outcome_json FROM agent_actions WHERE id = :id"),
        {"id": action_id},
    )
    action = row.fetchone()
    # approve_agent_action transitions an executed action to 'executed' (not
    # 'approved'): terminal_status = 'executed' when outcome.executed is True.
    assert action.status == "executed"
    assert action.outcome_json["po_number"].startswith("NAZM-")
    assert action.outcome_json["total_sar"] == 150.0

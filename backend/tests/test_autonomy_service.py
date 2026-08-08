"""Unit tests for autonomy evaluator and safe execution."""
import json
import pytest
from datetime import time
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4

from app.services.autonomy_service import evaluate_action, load_policy, execute_if_autonomous, dry_run_action


def _policy(dial: int, **kwargs):
    base = {"dial": dial}
    base.update(kwargs)
    return base


def test_evaluate_inform_only():
    mode = evaluate_action("restock", {"estimated_cost_sar": 100}, _policy(0))
    assert mode.mode == "inform"
    assert mode.safe is True


def test_evaluate_draft():
    mode = evaluate_action("restock", {"estimated_cost_sar": 100}, _policy(50))
    assert mode.mode == "draft"


def test_evaluate_auto_executes_when_safe():
    mode = evaluate_action("restock", {"estimated_cost_sar": 100}, _policy(100), confidence=0.95)
    assert mode.mode == "auto_execute"
    assert mode.safe is True


def test_evaluate_downgrades_over_ceiling():
    mode = evaluate_action("restock", {"estimated_cost_sar": 5000}, _policy(100, ceiling_sar=2000), confidence=0.95)
    assert mode.mode == "draft"
    assert mode.downgraded is True
    assert "ceiling" in mode.reason.lower()


def test_evaluate_downgrades_price_increase():
    mode = evaluate_action("pricing_increase", {"increase_pct": 12}, _policy(100, max_price_increase_pct=5), confidence=0.95)
    assert mode.mode == "draft"
    assert "price increase" in mode.reason.lower()


def test_evaluate_downgrades_quiet_hours():
    mode = evaluate_action("restock", {"estimated_cost_sar": 100}, _policy(100, quiet_hours_start=time(0,0), quiet_hours_end=time(23,59)), confidence=0.95)
    assert mode.mode == "draft"
    assert "quiet hours" in mode.reason.lower()


@pytest.mark.asyncio
async def test_load_policy_uses_default_when_missing(monkeypatch):
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(fetchone=MagicMock(return_value=None)))
    policy = await load_policy(db, uuid4(), "restock")
    assert policy["dial"] == 50
    assert policy["ceiling_sar"] == 2000


@pytest.mark.asyncio
async def test_execute_if_autonomous_not_found():
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(fetchone=MagicMock(return_value=None)))
    db.commit = AsyncMock()
    result = await execute_if_autonomous(db, uuid4())
    assert result["executed"] is False
    assert "not found" in result["reason"].lower()


@pytest.mark.asyncio
async def test_dry_run_action():
    action_id = uuid4()
    business_id = uuid4()
    row = MagicMock(
        dial=100,
        ceiling_sar=None,
        max_price_increase_pct=5,
        max_price_decrease_pct=None,
        max_quantity=None,
        quiet_hours_start=None,
        quiet_hours_end=None,
        require_2fa_above_sar=None,
    )
    row.id = action_id
    row.business_id = business_id
    row.action_type = "pricing_increase"
    row.status = "pending_approval"
    row.payload = {"increase_pct": 3}
    row.confidence = 0.95
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(fetchone=MagicMock(return_value=row)))
    result = await dry_run_action(db, action_id)
    assert result["ok"] is True
    assert result["mode"] == "auto_execute"

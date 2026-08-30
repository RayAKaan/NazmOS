"""Autonomy evaluator – maps the autonomy dial to safe execution modes.

Rules:
- dial 0        → inform only (human must act manually)
- dial 1-94     → draft / pending approval (one-tap confirm)
- dial 95-100   → auto-execute ONLY if guardrails pass

Guardrails are per-policy: spend ceiling, max price change %, quiet hours,
and optional 2FA threshold. If a guardrail blocks auto-execution, the action
is downgraded to pending_approval so the owner still sees it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from app.utils.clock import utcnow as _clock_utcnow

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent_action_executor import execute_agent_action
from app.utils.money import sar, decimal_value


DEFAULTS = {
    "restock": {"dial": 50, "ceiling_sar": Decimal("2000"), "max_price_increase_pct": None, "max_price_decrease_pct": None},
    "pricing_increase": {"dial": 20, "ceiling_sar": None, "max_price_increase_pct": Decimal("5"), "max_price_decrease_pct": None},
    "pricing_decrease": {"dial": 30, "ceiling_sar": None, "max_price_increase_pct": None, "max_price_decrease_pct": Decimal("10")},
    "cash_alert": {"dial": 0, "ceiling_sar": Decimal("0"), "max_price_increase_pct": None, "max_price_decrease_pct": None},
    "staff_schedule": {"dial": 0, "ceiling_sar": Decimal("0"), "max_price_increase_pct": None, "max_price_decrease_pct": None},
    "expiry_alert": {"dial": 50, "ceiling_sar": Decimal("500"), "max_price_increase_pct": None, "max_price_decrease_pct": None},
}


@dataclass
class AutonomyMode:
    mode: str  # inform, draft, auto_execute
    safe: bool
    reason: str
    policy: dict[str, Any]
    downgraded: bool = False


def _in_quiet_hours(quiet_start: time | None, quiet_end: time | None) -> bool:
    if quiet_start is None or quiet_end is None:
        return False
    # §12 Business Clock: use virtual clock for business-time-dependent logic.
    # Quiet hours are in local (KSA) time, so convert UTC → KSA (+3).
    now_utc = _clock_utcnow()
    from datetime import timezone, timedelta
    now_local = (now_utc + timedelta(hours=3)).time()
    if quiet_start < quiet_end:
        return quiet_start <= now_local <= quiet_end
    return now_local >= quiet_start or now_local <= quiet_end


def _coerce_time(value: Any) -> time | None:
    if value is None:
        return None
    if isinstance(value, time):
        return value
    if isinstance(value, str):
        return datetime.strptime(value, "%H:%M").time()
    return None


def _is_numeric(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float, Decimal))


async def load_policy(
    db: AsyncSession,
    business_id: UUID | str,
    action_type: str,
) -> dict[str, Any]:
    res = await db.execute(text("""
        SELECT action_type, dial, ceiling_sar, max_price_increase_pct,
               max_price_decrease_pct, max_quantity, quiet_hours_start,
               quiet_hours_end, require_2fa_above_sar
        FROM autonomy_policies
        WHERE business_id = :b AND action_type = :a AND is_active = true
    """), {"b": str(business_id), "a": action_type})
    row = res.fetchone()
    default = DEFAULTS.get(action_type, {"dial": 0}).copy()
    if row:
        default["dial"] = int(row.dial)
        if _is_numeric(row.ceiling_sar):
            default["ceiling_sar"] = sar(row.ceiling_sar)
        if _is_numeric(row.max_price_increase_pct):
            default["max_price_increase_pct"] = decimal_value(row.max_price_increase_pct)
        if _is_numeric(row.max_price_decrease_pct):
            default["max_price_decrease_pct"] = decimal_value(row.max_price_decrease_pct)
        if _is_numeric(row.max_quantity):
            default["max_quantity"] = decimal_value(row.max_quantity)
        default["quiet_hours_start"] = _coerce_time(row.quiet_hours_start)
        default["quiet_hours_end"] = _coerce_time(row.quiet_hours_end)
        if _is_numeric(row.require_2fa_above_sar):
            default["require_2fa_above_sar"] = sar(row.require_2fa_above_sar)
    return default


def evaluate_action(
    action_type: str,
    payload: dict[str, Any],
    policy: dict[str, Any],
    confidence: float = 0.0,
) -> AutonomyMode:
    from app.config import get_settings
    min_conf = getattr(get_settings(), "AGENT_AUTO_MIN_CONFIDENCE", 0.90)
    dial = int(policy.get("dial", 0))

    if dial == 0:
        return AutonomyMode("inform", True, "dial set to inform-only", policy)
    if dial < 95 or confidence < min_conf:
        if dial >= 95 and confidence < min_conf:
            return AutonomyMode(
                "draft", True,
                f"auto-execution dial requires confidence >= {min_conf:.2f}; downgraded to draft",
                policy, downgraded=True,
            )
        return AutonomyMode("draft", True, "approval required", policy)

    # Auto-execute path: run guardrails.
    reasons: list[str] = []
    downgraded = False

    ceiling = policy.get("ceiling_sar")
    value = _extract_value_sar(payload)
    if ceiling is not None and value is not None and value > ceiling:
        reasons.append(f"value SAR {value} exceeds auto-spend ceiling SAR {ceiling}")
        downgraded = True

    max_inc = policy.get("max_price_increase_pct")
    inc_pct = _extract_price_change_pct(payload, increase=True)
    if max_inc is not None and inc_pct is not None and inc_pct > max_inc:
        reasons.append(f"price increase {inc_pct}% exceeds max {max_inc}%")
        downgraded = True

    max_dec = policy.get("max_price_decrease_pct")
    dec_pct = _extract_price_change_pct(payload, increase=False)
    if max_dec is not None and dec_pct is not None and dec_pct > max_dec:
        reasons.append(f"price decrease {dec_pct}% exceeds max {max_dec}%")
        downgraded = True

    max_qty = policy.get("max_quantity")
    qty = _extract_quantity(payload)
    if max_qty is not None and qty is not None and qty > max_qty:
        reasons.append(f"quantity {qty} exceeds max auto quantity {max_qty}")
        downgraded = True

    if _in_quiet_hours(policy.get("quiet_hours_start"), policy.get("quiet_hours_end")):
        reasons.append("quiet hours active")
        downgraded = True

    require_2fa = policy.get("require_2fa_above_sar")
    if require_2fa is not None and value is not None and value > require_2fa:
        reasons.append(f"value SAR {value} requires 2FA above SAR {require_2fa}")
        downgraded = True

    if downgraded:
        return AutonomyMode(
            "draft", True,
            "auto-execution blocked by guardrails: " + "; ".join(reasons),
            policy, downgraded=True,
        )

    return AutonomyMode("auto_execute", True, "all guardrails passed", policy)


def _extract_value_sar(payload: dict[str, Any]) -> Decimal | None:
    for key in ("estimated_cost_sar", "estimated_value_sar", "total_sar", "value_sar", "suggested_price"):
        if key in payload and payload[key] is not None:
            try:
                return sar(payload[key])
            except Exception:
                continue
    return None


def _extract_price_change_pct(payload: dict[str, Any], increase: bool) -> Decimal | None:
    for key in ("increase_pct", "decrease_pct", "price_change_pct", "change_pct"):
        if key in payload and payload[key] is not None:
            try:
                return decimal_value(payload[key])
            except Exception:
                continue
    current = payload.get("current_price")
    suggested = payload.get("suggested_price")
    if current and suggested:
        try:
            cur = decimal_value(current)
            sug = decimal_value(suggested)
            if cur <= 0:
                return None
            pct = ((sug - cur) / cur) * 100
            if increase and pct > 0:
                return pct
            if not increase and pct < 0:
                return abs(pct)
        except Exception:
            return None
    return None


def _extract_quantity(payload: dict[str, Any]) -> Decimal | None:
    for key in ("recommended_qty", "quantity", "qty", "quantity_available"):
        if key in payload and payload[key] is not None:
            try:
                return decimal_value(payload[key])
            except Exception:
                continue
    return None


async def execute_if_autonomous(
    db: AsyncSession,
    action_id: UUID | str,
    current_user_id: UUID | str | None = None,
) -> dict[str, Any]:
    """Evaluate and, if safe, auto-execute a pending agent action.

    Returns a dict describing the result. The caller is responsible for HTTP
    status codes.
    """
    res = await db.execute(text("""
        SELECT id, business_id, action_type, status, payload, confidence
        FROM agent_actions
        WHERE id = :id
    """), {"id": str(action_id)})
    row = res.fetchone()
    if not row:
        return {"ok": False, "reason": "Action not found", "executed": False}

    if row.status != "pending_approval":
        return {"ok": False, "reason": f"Action status is {row.status}, not pending_approval", "executed": False}

    payload = row.payload if isinstance(row.payload, dict) else json.loads(row.payload or "{}")
    policy = await load_policy(db, row.business_id, row.action_type)
    mode = evaluate_action(row.action_type, payload, policy, confidence=float(row.confidence or 0))

    if mode.mode != "auto_execute":
        return {
            "ok": True,
            "executed": False,
            "mode": mode.mode,
            "reason": mode.reason,
            "downgraded": mode.downgraded,
        }

    # Execute deterministically.
    outcome = await execute_agent_action(db, row.business_id, row.id, row.action_type, payload)

    executed = bool(outcome.get("executed"))
    new_status = "auto_executed" if executed else "failed"
    await db.execute(text("""
        UPDATE agent_actions
        SET status = :status,
            was_auto_executed = :executed,
            applied_at = CASE WHEN :executed THEN NOW() ELSE applied_at END,
            outcome_json = CAST(:outcome AS JSON),
            decided_at = NOW(),
            decided_by = COALESCE(CAST(:uid AS UUID), decided_by),
            decision_note = 'Auto-executed by autonomy guardrails',
            updated_at = NOW()
        WHERE id = :id
    """), {
        "id": str(action_id),
        "status": new_status,
        "executed": executed,
        "outcome": json.dumps(outcome),
        "uid": str(current_user_id) if current_user_id else None,
    })
    await db.commit()

    return {
        "ok": True,
        "executed": executed,
        "mode": "auto_execute",
        "reason": mode.reason,
        "outcome": outcome,
    }


async def dry_run_action(
    db: AsyncSession,
    action_id: UUID | str,
) -> dict[str, Any]:
    """Show what execute_if_autonomous would do without mutating state."""
    res = await db.execute(text("""
        SELECT id, business_id, action_type, status, payload, confidence
        FROM agent_actions
        WHERE id = :id
    """), {"id": str(action_id)})
    row = res.fetchone()
    if not row:
        return {"ok": False, "reason": "Action not found"}

    payload = row.payload if isinstance(row.payload, dict) else json.loads(row.payload or "{}")
    policy = await load_policy(db, row.business_id, row.action_type)
    mode = evaluate_action(row.action_type, payload, policy, confidence=float(row.confidence or 0))

    return {
        "ok": True,
        "action_id": str(row.id),
        "action_type": row.action_type,
        "current_status": row.status,
        "mode": mode.mode,
        "safe": mode.safe,
        "reason": mode.reason,
        "downgraded": mode.downgraded,
        "policy": {
            "dial": int(policy.get("dial", 0)),
            "ceiling_sar": float(policy["ceiling_sar"]) if policy.get("ceiling_sar") is not None else None,
            "max_price_increase_pct": float(policy["max_price_increase_pct"]) if policy.get("max_price_increase_pct") is not None else None,
            "max_price_decrease_pct": float(policy["max_price_decrease_pct"]) if policy.get("max_price_decrease_pct") is not None else None,
            "max_quantity": float(policy["max_quantity"]) if policy.get("max_quantity") is not None else None,
        },
    }

"""Structured Business Goals + deterministic progress (Phase 4, §2–3).

Coexists with the free-form `goals` memory document — does not replace it. Every
measurable goal has baseline / target / current / direction / deadline; progress is
computed deterministically from business data or the Impact Ledger, never from vague
LLM output. Goals that cannot be measured reliably should not be forced into metrics.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _json(v: Any) -> str:
    return json.dumps(v, default=str)


async def create_goal(
    db: AsyncSession,
    business_id: UUID | str,
    *,
    title: str,
    metric: str,
    direction: str,
    target: float,
    baseline: float | None = None,
    deadline: date | None = None,
    priority: int = 3,
    source: str = "manual",
    source_key: str | None = None,
    commit: bool = True,
) -> UUID:
    import uuid
    goal_id = uuid.uuid4()
    await db.execute(text("""
        INSERT INTO business_goals
            (id, business_id, title, metric, direction, baseline, target, deadline,
             priority, status, source, source_key, created_at, updated_at)
        VALUES
            (:id, :b, :title, :metric, :dir, :baseline, :target, :deadline,
             :priority, 'active', :source, :key, :now, :now)
    """), {
        "id": str(goal_id), "b": str(business_id), "title": title, "metric": metric,
        "dir": direction, "baseline": baseline, "target": target,
        "deadline": deadline, "priority": priority, "source": source, "key": source_key,
        "now": datetime.now(timezone.utc),
    })
    if commit:
        await db.commit()
    return goal_id


async def _measure_current(db: AsyncSession, business_id: UUID | str, goal: Any) -> Decimal | None:
    """Deterministic measurement of a goal's current value, by source."""
    source = goal.source
    if source == "impact_ledger":
        # sum observed impact for a specific impact_type (source_key), or total observed.
        if goal.source_key:
            res = await db.execute(text("""
                SELECT COALESCE(SUM(amount_sar), 0) FROM impact_ledger
                WHERE business_id = :b AND impact_type = :t AND verified = true
            """), {"b": str(business_id), "t": goal.source_key})
        else:
            res = await db.execute(text("""
                SELECT COALESCE(SUM(amount_sar), 0) FROM impact_ledger
                WHERE business_id = :b AND verified = true
            """), {"b": str(business_id)})
        return Decimal(str(res.scalar() or 0))

    if source == "inventory" and goal.source_key == "dead_stock_value":
        from app.services.agent_tools import execute_agent_tool
        dead = await execute_agent_tool("get_dead_stock_summary", {"days_no_sale": 30}, business_id, db)
        if isinstance(dead, dict):
            return Decimal(str(dead.get("total_stuck_sar") or 0))
        return None

    if source == "margin" and goal.source_key == "gross_margin":
        res = await db.execute(text("""
            SELECT COALESCE(AVG((i.sell_price - i.cost_price) / NULLIF(i.sell_price, 0)), 0)
            FROM items i WHERE i.business_id = :b AND i.is_active = true AND i.sell_price > 0
        """), {"b": str(business_id)})
        avg = res.scalar()
        return Decimal(str(round(float(avg or 0) * 100, 2))) if avg is not None else None

    if source == "sales" and goal.source_key in ("revenue", "units"):
        # Deterministic sales metric over the trailing 30 days (§11). Dialect-safe.
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        col = "total_sar" if goal.source_key == "revenue" else "quantity"
        res = await db.execute(text(f"""
            SELECT COALESCE(SUM({col}), 0) FROM transactions
            WHERE business_id = :b AND transaction_at >= :cutoff
        """), {"b": str(business_id), "cutoff": cutoff})  # nosec B608
        return Decimal(str(res.scalar() or 0))

    # manual / unknown → current_value already set, or None.
    return None


def compute_progress(
    baseline: Decimal | None,
    current: Decimal | None,
    target: Decimal,
    direction: str,
) -> dict[str, Any]:
    """Deterministic progress % + remaining gap + trajectory (never LLM-derived)."""
    if current is None:
        return {"progress_pct": None, "remaining_gap": None, "trajectory": "unknown"}

    current = Decimal(str(current))
    target = Decimal(str(target))

    if direction == "decrease":
        # progress = (baseline - current) / (baseline - target)
        if baseline is None:
            return {"progress_pct": None, "remaining_gap": current - target, "trajectory": "unknown"}
        baseline = Decimal(str(baseline))
        denom = baseline - target
        if denom == 0:
            progress = 100.0 if current <= target else 0.0
        else:
            progress = (baseline - current) / denom * 100
        gap = current - target  # positive = still above target
        achieved = current <= target
    elif direction == "increase":
        if baseline is None:
            return {"progress_pct": None, "remaining_gap": target - current, "trajectory": "unknown"}
        baseline = Decimal(str(baseline))
        denom = target - baseline
        if denom == 0:
            progress = 100.0 if current >= target else 0.0
        else:
            progress = (current - baseline) / denom * 100
        gap = target - current
        achieved = current >= target
    else:  # maintain — within band
        # treat as achieved if current is within ±5% of target
        band = abs(target) * Decimal("0.05") if target != 0 else Decimal("1")
        achieved = abs(current - target) <= band
        progress = 100.0 if achieved else 0.0
        gap = abs(current - target)

    progress = max(0.0, min(100.0, float(progress)))
    trajectory = "achieved" if achieved else "on_track" if progress >= 50 else "at_risk"
    return {
        "progress_pct": round(progress, 1),
        "remaining_gap": round(float(gap), 2),
        "trajectory": trajectory,
    }


async def _measure_all_current(db: AsyncSession, business_id: UUID | str) -> dict[str, Any]:
    """Measure all goals' current values at once (used by the scheduler). Returns
    goal_id -> measured Decimal (or None)."""
    res = await db.execute(text("""
        SELECT id, source, source_key, baseline, target, direction
        FROM business_goals WHERE business_id = :b AND status != 'paused'
    """), {"b": str(business_id)})
    measured: dict[str, Any] = {}
    for r in res.fetchall():
        m = await _measure_current(db, business_id, r)
        measured[str(r.id)] = m
    return measured


async def snapshot_goal_progress(
    db: AsyncSession,
    business_id: UUID | str,
    source: str = "scheduled",
    commit: bool = True,
) -> dict[str, Any]:
    """Record a historical snapshot of every active goal's progress (idempotent per
    goal+hour via the unique constraint). Called by the Celery scheduler (§9)."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    res = await db.execute(text("""
        SELECT id, title, metric, direction, baseline, target, current_value, source
        FROM business_goals WHERE business_id = :b AND status != 'paused'
    """), {"b": str(business_id)})
    goals = res.fetchall()
    snapshots = 0
    for g in goals:
        measured = await _measure_current(db, business_id, g)
        if measured is None:
            continue
        progress = compute_progress(
            Decimal(str(g.baseline)) if g.baseline is not None else None,
            measured,
            Decimal(str(g.target)),
            g.direction,
        )
        await db.execute(text("""
            INSERT INTO goal_progress_history
                (id, goal_id, business_id, measured_value, progress_pct, trajectory, source, measured_at)
            VALUES
                (:id, :gid, :b, :val, :pct, :traj, :src, :at)
            ON CONFLICT (goal_id, measured_at) DO UPDATE SET
                measured_value = EXCLUDED.measured_value,
                progress_pct = EXCLUDED.progress_pct,
                trajectory = EXCLUDED.trajectory,
                source = EXCLUDED.source
        """), {
            "id": str(uuid.uuid4()), "gid": str(g.id), "b": str(business_id),
            "val": measured, "pct": progress["progress_pct"],
            "traj": progress["trajectory"], "src": source, "at": now,
        })
        snapshots += 1
    if commit:
        await db.commit()
    return {"snapshots": snapshots, "measured_at": now.isoformat()}


async def goal_history(
    db: AsyncSession,
    business_id: UUID | str,
    goal_id: UUID | str,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Historical progress snapshots for one goal (oldest → newest)."""
    res = await db.execute(text("""
        SELECT measured_value, progress_pct, trajectory, source, measured_at
        FROM goal_progress_history
        WHERE business_id = :b AND goal_id = :gid
        ORDER BY measured_at DESC LIMIT :lim
    """), {"b": str(business_id), "gid": str(goal_id), "lim": limit})
    rows = list(res.fetchall())
    rows.reverse()
    return [
        {
            "measured_value": float(r.measured_value),
            "progress_pct": float(r.progress_pct) if r.progress_pct is not None else None,
            "trajectory": r.trajectory,
            "source": r.source,
            "measured_at": r.measured_at.isoformat() if r.measured_at else None,
        }
        for r in rows
    ]


def enrich_trajectory(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic trajectory analysis (§10): on_track | at_risk | off_track | achieved |
    regressing, computed from measured history — never LLM opinion."""
    if not history:
        return {"trajectory": "unknown", "note": "No history yet"}
    latest = history[-1]
    if latest.get("trajectory") == "achieved":
        return {"trajectory": "achieved", "note": "Target reached"}

    # Regressing: latest measured value moved away from target vs the previous snapshot.
    if len(history) >= 2:
        prev = history[-2]
        prev_pct = prev.get("progress_pct")
        cur_pct = latest.get("progress_pct")
        if prev_pct is not None and cur_pct is not None and cur_pct < prev_pct:
            return {"trajectory": "regressing", "note": "Progress decreased vs previous measurement"}

    pct = latest.get("progress_pct")
    if pct is None:
        return {"trajectory": "unknown", "note": "Progress not computable (missing baseline)"}
    if pct >= 50:
        return {"trajectory": "on_track", "note": f"{pct:.0f}% complete"}
    return {"trajectory": "at_risk", "note": f"Only {pct:.0f}% complete — likely to miss target"}


def estimate_miss_days(
    history: list[dict[str, Any]],
    *,
    current_value: Decimal | None,
    target: Decimal,
    direction: str,
    deadline: date | None,
) -> dict[str, Any]:
    """§11: deterministic "will miss target by N days" projection from measured history.

    Requires ≥2 snapshots with timestamps; otherwise reports "insufficient data" rather
    than fabricating a trajectory.
    """
    if not deadline or current_value is None:
        return {"estimate": None, "reason": "insufficient data"}

    if len(history) < 2:
        return {"estimate": None, "reason": "insufficient data to estimate target date"}

    # per-day rate of change over the observed window (last snapshot vs first).
    first = history[0]
    last = history[-1]
    try:
        first_ts = datetime.fromisoformat(first["measured_at"])
        last_ts = datetime.fromisoformat(last["measured_at"])
    except (KeyError, TypeError, ValueError):
        return {"estimate": None, "reason": "insufficient data to estimate target date"}

    span_days = max(1.0, (last_ts - first_ts).total_seconds() / 86400)
    delta_value = float(last["measured_value"]) - float(first["measured_value"])
    rate_per_day = delta_value / span_days

    remaining = float(target) - float(current_value)
    if direction == "decrease":
        # remaining is negative when above target (current > target); rate must be negative.
        if rate_per_day >= 0:
            return {"estimate": None, "reason": "no progress toward target (rate >= 0)"}
        days_to_target = remaining / rate_per_day  # both negative → positive days
    else:
        if rate_per_day <= 0:
            return {"estimate": None, "reason": "no progress toward target (rate <= 0)"}
        days_to_target = remaining / rate_per_day

    if days_to_target <= 0:
        return {"estimate": 0, "reason": "on track to reach target on time", "projected_date": deadline.isoformat()}

    projected = last_ts + timedelta(days=days_to_target)
    late_days = max(0, (projected.date() - deadline).days)
    return {
        "estimate": late_days if late_days > 0 else 0,
        "reason": f"projected {late_days} day(s) late" if late_days > 0 else "on track",
        "projected_date": projected.date().isoformat(),
        "rate_per_day": round(rate_per_day, 4),
    }


async def goal_alignment_chain(db: AsyncSession, business_id: UUID | str, goal_id: UUID | str) -> dict[str, Any]:
    """§12: the full goal → findings → actions → impact → progress chain, queryable."""
    goal = await db.execute(text("""
        SELECT id, title, metric, direction, baseline, target FROM business_goals
        WHERE id = :gid AND business_id = :b
    """), {"gid": str(goal_id), "b": str(business_id)})
    grow = goal.fetchone()
    if not grow:
        return {"ok": False, "reason": "goal not found"}

    # §10: use the curated goal → domain mapping (not metric-name heuristics).
    from app.services.goal_domains import categories_for_goal, domains_for_goal
    categories = categories_for_goal(grow.metric) or [grow.metric, grow.metric.replace("_", " ")]
    domains = domains_for_goal(grow.metric) or categories

    findings = await db.execute(text("""
        SELECT id, title, category, severity, estimated_financial_impact_sar, status, domain
        FROM findings
        WHERE business_id = :b AND (category = ANY(:cats) OR domain = ANY(:domains))
        ORDER BY created_at DESC LIMIT 50
    """), {"b": str(business_id), "cats": categories, "domains": domains})

    actions = await db.execute(text("""
        SELECT id, action_type, status, estimated_value_sar, finding_id
        FROM agent_actions
        WHERE business_id = :b AND finding_id IN (
            SELECT id FROM findings WHERE business_id = :b AND (category = ANY(:cats) OR domain = ANY(:domains))
        )
        ORDER BY created_at DESC LIMIT 50
    """), {"b": str(business_id), "cats": categories, "domains": domains})

    impact = await db.execute(text("""
        SELECT COALESCE(SUM(amount_sar), 0) AS observed, COALESCE(SUM(CASE WHEN verified THEN amount_sar ELSE 0 END), 0) AS verified
        FROM impact_ledger
        WHERE business_id = :b AND finding_id IN (SELECT id FROM findings WHERE business_id = :b)
    """), {"b": str(business_id)})

    progress = await list_goals_with_progress(db, business_id)
    this_goal = next((g for g in progress if g["id"] == str(goal_id)), None)

    return {
        "goal": {
            "id": str(grow.id), "title": grow.title, "metric": grow.metric,
            "direction": grow.direction, "baseline": float(grow.baseline) if grow.baseline else None,
            "target": float(grow.target),
        },
        "findings": [
            {"id": str(r.id), "title": r.title, "category": r.category, "severity": r.severity,
             "impact_sar": float(r.estimated_financial_impact_sar) if r.estimated_financial_impact_sar is not None else None,
             "status": r.status}
            for r in findings.fetchall()
        ],
        "actions": [
            {"id": str(r.id), "action_type": r.action_type, "status": r.status,
             "finding_id": str(r.finding_id) if r.finding_id else None,
             "estimated_value_sar": float(r.estimated_value_sar) if r.estimated_value_sar is not None else None}
            for r in actions.fetchall()
        ],
        "impact": {
            "observed_sar": float((impact.fetchone() or (0, 0))[0] or 0),
        },
        "progress": this_goal,
    }


async def list_goals_with_progress(db: AsyncSession, business_id: UUID | str) -> list[dict[str, Any]]:
    """List goals and compute deterministic progress for each."""
    res = await db.execute(text("""
        SELECT id, title, metric, direction, baseline, target, current_value, deadline,
               priority, status, source, source_key, created_at
        FROM business_goals WHERE business_id = :b ORDER BY priority ASC, created_at DESC
    """), {"b": str(business_id)})
    out = []
    for r in res.fetchall():
        current = Decimal(str(r.current_value)) if r.current_value is not None else None
        if current is None:
            measured = await _measure_current(db, business_id, r)
            if measured is not None:
                current = measured
        baseline = Decimal(str(r.baseline)) if r.baseline is not None else None
        target = Decimal(str(r.target)) if r.target is not None else Decimal("0")
        progress = compute_progress(baseline, current, target, r.direction)
        out.append({
            "id": str(r.id),
            "title": r.title,
            "metric": r.metric,
            "direction": r.direction,
            "baseline": float(baseline) if baseline is not None else None,
            "target": float(target),
            "current_value": float(current) if current is not None else None,
            "deadline": r.deadline.isoformat() if r.deadline else None,
            "priority": r.priority,
            "status": r.status,
            "source": r.source,
            **progress,
        })
    return out

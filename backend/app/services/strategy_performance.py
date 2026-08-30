"""Strategy Performance Engine (Phase 8, §7–11).

Aggregates performance by strategy/action type from the existing canonical outcome
records (LearnedOutcome + ImpactLedger) — no new learning database. Metrics are
deterministic, split into observed vs estimated value, and segmented by category when
evidence is sufficient. Minimum-evidence thresholds are configurable, never a single
success dominating selection.

success_rate      = verified successes / attempts
effectiveness     = observed impact / expected impact (where expected > 0)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings

_settings = get_settings()

# §9: deterministic minimum-evidence thresholds (configurable, conservative defaults).
MIN_EVIDENCE_WEAK = 1        # insufficient
MIN_EVIDENCE_PRELIMINARY = 3  # preliminary
MIN_EVIDENCE_STRONG = 10      # stronger signal

# §11: recency half-life (days). An outcome this old counts for half its weight.
RECENCY_HALF_LIFE_DAYS = float(getattr(_settings, "RECENCY_HALF_LIFE_DAYS", 90.0))


def recency_weight(created_at: Any, now: datetime | None = None) -> float:
    """Deterministic exponential recency decay: weight = 2^(-age / half_life).

    Recent outcomes → weight ~1.0; an outcome `half_life` days old → 0.5. Age 0 → 1.0.
    Never negative; never rewrites history (this is a *weight*, not an overwrite, §12).
    """
    now = now or datetime.now(timezone.utc)
    if created_at is None:
        return 1.0
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at)
        except ValueError:
            return 1.0
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_seconds = max(0.0, (now - created_at).total_seconds())
    age_days = age_seconds / 86400.0
    return 2.0 ** (-age_days / RECENCY_HALF_LIFE_DAYS)


def evidence_tier(attempts: int) -> str:
    if attempts < MIN_EVIDENCE_PRELIMINARY:
        return "insufficient"
    if attempts < MIN_EVIDENCE_STRONG:
        return "preliminary"
    return "strong"


@dataclass
class StrategySummary:
    action_type: str
    attempts: int
    approved: int
    rejected: int
    executed: int
    verified: int
    failed: int
    observed_value_sar: float
    expected_value_sar: float
    success_rate: float | None
    effectiveness: float | None
    evidence_tier: str


# §7: attribution weighting — weak business-level attribution must not influence strategy
# performance as strongly as direct verified attribution.
ATTRIBUTION_WEIGHT = {
    "direct": 1.0,
    "partial": 0.7,
    "business_level": 0.3,
    "estimated": 0.0,
    "unattributable": 0.0,
}


async def strategy_summaries(db: AsyncSession, business_id: UUID | str) -> list[dict[str, Any]]:
    """Per-strategy aggregate from LearnedOutcome + ImpactLedger.

    Observed value is attribution-weighted from ImpactLedger (§7): direct=1.0,
    partial=0.7, business_level=0.3, estimated/unattributable=0. Verified-success counts
    come from LearnedOutcome (executed + actual impact present).
    """
    res = await db.execute(text("""
        SELECT lo.action_type,
               COUNT(lo.id) AS attempts,
               COALESCE(SUM(CASE WHEN lo.approval IN ('approved','auto_executed') THEN 1 ELSE 0 END), 0) AS approved,
               COALESCE(SUM(CASE WHEN lo.approval = 'rejected' THEN 1 ELSE 0 END), 0) AS rejected,
               COALESCE(SUM(CASE WHEN lo.execution_result->>'executed' = 'true' THEN 1 ELSE 0 END), 0) AS executed,
               COALESCE(SUM(CASE WHEN lo.actual_impact_sar IS NOT NULL THEN 1 ELSE 0 END), 0) AS verified,
               COALESCE(SUM(CASE WHEN lo.approval IN ('approved','auto_executed') AND lo.execution_result->>'executed' != 'true' THEN 1 ELSE 0 END), 0) AS failed,
               COALESCE(SUM(lo.actual_impact_sar), 0) AS observed_value,
               COALESCE(SUM(lo.expected_impact_sar), 0) AS expected_value
        FROM learned_outcomes lo
        WHERE lo.business_id = :b
        GROUP BY lo.action_type
        ORDER BY attempts DESC
    """), {"b": str(business_id)})

    # §7: attribution-weighted observed value from ImpactLedger.
    attr = await db.execute(text("""
        SELECT a.action_type,
               COALESCE(SUM(il.amount_sar * CASE il.attribution
                   WHEN 'direct' THEN 1.0 WHEN 'partial' THEN 0.7 WHEN 'business_level' THEN 0.3
                   ELSE 0.0 END), 0) AS weighted_observed,
               COALESCE(SUM(il.amount_sar), 0) AS raw_observed
        FROM impact_ledger il
        JOIN agent_actions a ON a.id = il.agent_action_id
        WHERE il.business_id = :b AND il.verified = true
        GROUP BY a.action_type
    """), {"b": str(business_id)})
    weighted = {r.action_type: (float(r.weighted_observed or 0), float(r.raw_observed or 0))
                for r in attr.fetchall()}

    out = []
    for r in res.fetchall():
        attempts = int(r.attempts or 0)
        verified = int(r.verified or 0)
        w_obs, raw_obs = weighted.get(r.action_type, (0.0, 0.0))
        expected = float(r.expected_value or 0)
        out.append({
            "action_type": r.action_type,
            "attempts": attempts,
            "approved": int(r.approved or 0),
            "rejected": int(r.rejected or 0),
            "executed": int(r.executed or 0),
            "verified": verified,
            "failed": int(r.failed or 0),
            "observed_value_sar": round(w_obs, 2),      # attribution-weighted
            "raw_observed_value_sar": round(raw_obs, 2),  # unweighted, for transparency
            "expected_value_sar": round(expected, 2),
            "success_rate": round(verified / attempts, 3) if attempts else None,
            "effectiveness": round(w_obs / expected, 3) if expected > 0 else None,
            "evidence_tier": evidence_tier(attempts),
        })
    return out


async def strategy_summary(db: AsyncSession, business_id: UUID | str, action_type: str) -> dict[str, Any]:
    summaries = await strategy_summaries(db, business_id)
    for s in summaries:
        if s["action_type"] == action_type:
            return s
    return {
        "action_type": action_type, "attempts": 0, "approved": 0, "rejected": 0,
        "executed": 0, "verified": 0, "failed": 0, "observed_value_sar": 0.0,
        "expected_value_sar": 0.0, "success_rate": None, "effectiveness": None,
        "evidence_tier": "insufficient",
    }


async def strategy_summary_recency(db: AsyncSession, business_id: UUID | str, action_type: str) -> dict[str, Any]:
    """§11–13: recency-weighted view of a strategy, WITHOUT erasing raw history.

    Returns raw counts (unchanged) plus a recency-weighted success_rate/effectiveness where
    each outcome's contribution is scaled by `recency_weight(created_at)`. A tiny recent
    sample cannot overpower a large raw sample: recency only shifts `relevance`, never the
    underlying `evidence_tier` (which stays based on raw attempt count, §13).
    """
    res = await db.execute(text("""
        SELECT created_at, approval, execution_result, actual_impact_sar, expected_impact_sar
        FROM learned_outcomes
        WHERE business_id = :b AND action_type = :t
    """), {"b": str(business_id), "t": action_type})

    weighted_success = 0.0
    weight_sum = 0.0
    weighted_observed = 0.0
    weighted_expected = 0.0
    attempts = 0
    for r in res.fetchall():
        attempts += 1
        w = recency_weight(r.created_at)
        weight_sum += w
        executed = False
        er = r.execution_result
        if isinstance(er, dict):
            executed = bool(er.get("executed"))
        elif isinstance(er, str):
            try:
                executed = bool(__import__("json").loads(er).get("executed"))
            except Exception:
                pass
        if executed:
            weighted_success += w
        if r.actual_impact_sar is not None:
            weighted_observed += float(r.actual_impact_sar or 0) * w
        if r.expected_impact_sar is not None:
            weighted_expected += float(r.expected_impact_sar or 0) * w

    raw = await strategy_summary(db, business_id, action_type)
    if weight_sum <= 0:
        return {**raw, "recency_weighted_success_rate": raw.get("success_rate"),
                "recency_weighted_effectiveness": raw.get("effectiveness"),
                "recency_weight_sum": 0.0}

    rw_success = round(weighted_success / weight_sum, 3) if weight_sum else None
    rw_eff = round(weighted_observed / weighted_expected, 3) if weighted_expected > 0 else None
    return {
        **raw,
        "recency_weighted_success_rate": rw_success,
        "recency_weighted_effectiveness": rw_eff,
        "recency_weight_sum": round(weight_sum, 3),
        # raw evidence tier unchanged — recency does not erase history (§12–13).
    }


async def strategy_by_category(db: AsyncSession, business_id: UUID | str, action_type: str) -> list[dict[str, Any]]:
    """Contextual segmentation by finding category (§8). Only returns segments with ≥
    MIN_EVIDENCE_PRELIMINARY attempts (no statistically meaningless tiny-sample ranks)."""
    res = await db.execute(text("""
        SELECT f.category,
               COUNT(lo.id) AS attempts,
               COALESCE(SUM(CASE WHEN lo.actual_impact_sar IS NOT NULL THEN 1 ELSE 0 END), 0) AS verified,
               COALESCE(SUM(lo.actual_impact_sar), 0) AS observed_value,
               COALESCE(SUM(lo.expected_impact_sar), 0) AS expected_value
        FROM learned_outcomes lo
        JOIN findings f ON f.id = lo.finding_id
        WHERE lo.business_id = :b AND lo.action_type = :t
        GROUP BY f.category
        ORDER BY attempts DESC
    """), {"b": str(business_id), "t": action_type})

    out = []
    for r in res.fetchall():
        attempts = int(r.attempts or 0)
        if attempts < MIN_EVIDENCE_PRELIMINARY:
            continue  # §8/§9: do not emit meaningless rankings from tiny samples
        verified = int(r.verified or 0)
        observed = float(r.observed_value or 0)
        expected = float(r.expected_value or 0)
        out.append({
            "category": r.category,
            "attempts": attempts,
            "verified": verified,
            "success_rate": round(verified / attempts, 3) if attempts else None,
            "observed_value_sar": round(observed, 2),
            "expected_value_sar": round(expected, 2),
            "effectiveness": round(observed / expected, 3) if expected > 0 else None,
        })
    return out


async def best_strategy_for_finding(
    db: AsyncSession,
    business_id: UUID | str,
    candidate_action_types: list[str],
    finding_category: str | None = None,
    regime_state: str = "no_signal",
) -> dict[str, Any]:
    """§12/§14/§17 + Phase 12 §Part 2: rank candidate strategies by historical effectiveness
    for this business (and this category when evidence exists), adjusted by recency and
    regime relevance. Deterministic; policy is evaluated separately and never bypassed (§13).

    Contextual score =
        (0.6·effectiveness + 0.4·success_rate)          [evidence-tier weighted]
        × recency_relevance                             [recency-weighted success vs raw]
        × regime_relevance                              [business materially changed?]

    Historical effectiveness remains visible in every returned item; the regime multiplier
    only down-weights *current relevance*, never erases history (§Part 10).
    """
    from app.services.regime_detection import regime_relevance_multiplier

    ranked = []
    regime_relevance = regime_relevance_multiplier(regime_state)
    for action_type in candidate_action_types:
        overall = await strategy_summary(db, business_id, action_type)
        recency = await strategy_summary_recency(db, business_id, action_type)
        seg = None
        if finding_category:
            for s in await strategy_by_category(db, business_id, action_type):
                if s["category"] == finding_category:
                    seg = s
                    break

        # Prefer contextual success rate when available, else overall.
        success_rate = (seg or {}).get("success_rate") or overall.get("success_rate")
        effectiveness = (seg or {}).get("effectiveness") or overall.get("effectiveness")
        attempts = overall.get("attempts", 0)

        # Deterministic base score: effectiveness first, then success rate, gated by evidence.
        tier = evidence_tier(attempts)
        tier_weight = {"insufficient": 0.0, "preliminary": 0.5, "strong": 1.0}[tier]
        base_score = 0.0
        if effectiveness is not None:
            base_score += float(effectiveness) * 0.6 * tier_weight
        if success_rate is not None:
            base_score += float(success_rate) * 0.4 * tier_weight

        # Recency relevance: how much recent outcomes align vs raw history (bounded 0.3–1.0
        # so a stale strategy is discounted but not zeroed; insufficient data → 1.0).
        rw_success = recency.get("recency_weighted_success_rate")
        if rw_success is None or overall.get("success_rate") is None:
            recency_relevance = 1.0
        else:
            raw_sr = overall.get("success_rate") or 0.0
            recency_relevance = max(0.3, min(1.0, 0.5 + (rw_success - raw_sr)))

        contextual_score = base_score * recency_relevance * regime_relevance

        ranked.append({
            "action_type": action_type,
            "score": round(contextual_score, 3),
            "base_score": round(base_score, 3),
            "success_rate": success_rate,
            "effectiveness": effectiveness,
            "recency_weighted_success_rate": rw_success,
            "recency_relevance": round(recency_relevance, 3),
            "regime_relevance": regime_relevance,
            "regime_state": regime_state,
            "evidence_tier": tier,
            "attempts": attempts,
            "contextual": seg is not None,
        })

    ranked.sort(key=lambda r: r["score"], reverse=True)
    return {
        "ranking": ranked,
        "note": "Deterministic ranking from historical outcomes × recency × regime relevance; policy is evaluated separately.",
    }

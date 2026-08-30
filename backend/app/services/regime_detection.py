"""Regime-change detection (Phase 11, §Part 9–10).

A conservative, deterministic signal — NOT causal reasoning, NOT LLM math. Compares a
recent window's central tendency against a historical baseline; declares
`no_signal` / `possible_change` / `supported_change` / `insufficient_data` based on a
documented relative-deviation threshold and minimum sample sizes.

Never erases history (§Part 10): it only produces a *relevance* multiplier that strategy
performance may apply to down-weight older evidence when the business materially changed.
"""
from __future__ import annotations
from app.utils.clock import utcnow

import math
from typing import Any

from app.config import get_settings

_settings = get_settings()

# Documented thresholds (conservative defaults; configurable).
# possible_change when recent mean deviates ≥35% from baseline; supported_change ≥70%.
REGIME_RELATIVE_DEVIATION = float(getattr(_settings, "REGIME_RELATIVE_DEVIATION", 0.35))
REGIME_MIN_RECENT_SAMPLES = int(getattr(_settings, "REGIME_MIN_RECENT_SAMPLES", 3))
REGIME_MIN_HISTORICAL_SAMPLES = int(getattr(_settings, "REGIME_MIN_HISTORICAL_SAMPLES", 6))


def detect_regime(
    historical: list[float],
    recent: list[float],
) -> dict[str, Any]:
    """Deterministic regime signal.

    historical = older samples (baseline), recent = newest samples.
    Returns {state, deviation_ratio, historical_mean, recent_mean, note}.
    """
    hist = [float(x) for x in (historical or []) if x is not None]
    rec = [float(x) for x in (recent or []) if x is not None]

    if len(rec) < REGIME_MIN_RECENT_SAMPLES or len(hist) < REGIME_MIN_HISTORICAL_SAMPLES:
        return {"state": "insufficient_data", "deviation_ratio": None,
                "historical_mean": None, "recent_mean": None,
                "note": "Insufficient samples to assess regime change."}

    hist_mean = sum(hist) / len(hist)
    rec_mean = sum(rec) / len(rec)

    if hist_mean == 0:
        # Avoid divide-by-zero; a shift from zero baseline to non-zero is a signal only if large.
        ratio = None if rec_mean == 0 else float("inf")
        state = "supported_change" if rec_mean != 0 else "no_signal"
    else:
        ratio = abs(rec_mean - hist_mean) / abs(hist_mean)
        if ratio <= REGIME_RELATIVE_DEVIATION:
            state = "no_signal"
        elif ratio <= REGIME_RELATIVE_DEVIATION * 2:
            state = "possible_change"
        else:
            state = "supported_change"

    return {
        "state": state,
        "deviation_ratio": round(ratio, 3) if ratio is not None and math.isfinite(ratio) else None,
        "historical_mean": round(hist_mean, 3),
        "recent_mean": round(rec_mean, 3),
        "note": "Deterministic relative-deviation signal; correlation, not causation.",
    }


def regime_relevance_multiplier(state: str) -> float:
    """§Part 10: how much historical strategy evidence should weigh given the regime signal.

    no_signal / insufficient_data → 1.0 (full historical relevance)
    possible_change            → 0.7
    supported_change           → 0.4
    Historical evidence is never erased — only its relevance to the *current* decision is
    reduced.
    """
    return {
        "no_signal": 1.0,
        "insufficient_data": 1.0,
        "possible_change": 0.7,
        "supported_change": 0.4,
    }.get(state, 1.0)


async def detect_business_regime(
    db,
    business_id: UUID | str,
    *,
    recent_days: int = 7,
    historical_days: int = 28,
) -> dict[str, Any]:
    """Deterministic business-level regime signal from daily sales velocity: recent window
    (default 7d) vs prior historical window (default 28d before that). Returns the
    `detect_regime` result plus the relevance multiplier. Correlation, not causation."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import text

    now = utcnow()
    recent_cutoff = now - timedelta(days=recent_days)
    hist_cutoff = now - timedelta(days=historical_days)

    rows = await db.execute(text("""
        SELECT DATE(transaction_at) AS d, SUM(quantity) AS qty
        FROM transactions
        WHERE business_id = :b AND transaction_at >= :hist_cutoff
        GROUP BY DATE(transaction_at)
        ORDER BY d
    """), {"b": str(business_id), "hist_cutoff": hist_cutoff})

    historical: list[float] = []
    recent: list[float] = []
    for r in rows.fetchall():
        day = r.d
        qty = float(r.qty or 0)
        if isinstance(day, str):
            day = datetime.fromisoformat(day[:10]).replace(tzinfo=timezone.utc)
        if day < recent_cutoff:
            historical.append(qty)
        else:
            recent.append(qty)

    result = detect_regime(historical, recent)
    result["relevance_multiplier"] = regime_relevance_multiplier(result["state"])
    return result

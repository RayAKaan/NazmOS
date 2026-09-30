"""Impact quantification.

The engine answers "how much does this matter?" and — critically — **never
collapses the impact ladder**:

    POTENTIAL → EXPECTED → APPROVED → EXECUTED → VERIFIED

Only ``POTENTIAL`` and ``EXPECTED`` are ever produced here. ``APPROVED``,
``EXECUTED`` and ``VERIFIED`` are produced by the Loop after governance,
execution and reconciliation. Intelligence must never claim recovered cash from
a potential estimate.

Every estimate exposes its formula and assumptions.
"""
from __future__ import annotations

from typing import Any, Optional

from app.services.intelligence.contracts import (
    BusinessContext,
    ImpactEstimate,
    ImpactKind,
    RootCause,
    RootCauseSupportLevel,
    Signal,
)

IMPACT_CALCULATION_VERSION = "impact-v1"

# Deterministic recoverable fractions by cause. These are business policy, versioned
# with the formula, and are applied ONLY to Orbit's recoverable range.
RECOVERABLE_FRACTION_BY_CAUSE: dict[str, float] = {
    "SLOW_STOCK_CONVERSION": 0.40,
    "INVENTORY_CASH_TRAPPED": 0.35,
    "LOW_DEMAND": 0.25,
    "SUPPLIER_COST_INCREASE": 0.30,
    "SELLING_PRICE_MISMATCH": 0.30,
    "EXCESSIVE_DISCOUNTING": 0.20,
    "SUPPLIER_LEAD_TIME": 0.15,
    "REORDER_THRESHOLD_LOW": 0.20,
    "EXPIRY_REMINDER": 0.10,
}

# Potential impact is discounted by evidence strength. An UNKNOWN cause can never
# produce a headline number.
SUPPORT_DISCOUNT: dict[RootCauseSupportLevel, float] = {
    RootCauseSupportLevel.OBSERVED: 1.0,
    RootCauseSupportLevel.SUPPORTED: 0.8,
    RootCauseSupportLevel.POSSIBLE: 0.4,
    RootCauseSupportLevel.UNKNOWN: 0.0,
}

# The optimistic upper bound of the expected impact, relative to potential.
EXPECTED_UPLIFT = 0.30

# Never present a sub-SAR amount as a headline impact.
MIN_IMMATERIAL_SAR = 1.0


def _exposure(context: BusinessContext, key: str) -> Optional[float]:
    exposures = context.exposures or {}
    if not isinstance(exposures, dict):
        return None
    raw = exposures.get(key)
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, dict):
        value = raw.get("value")
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None
    return None


def _recoverable_range(context: BusinessContext) -> tuple[Optional[float], Optional[float]]:
    """Orbit's explicit recoverable range, if it produced one."""
    exposures = context.exposures or {}
    if not isinstance(exposures, dict):
        return None, None
    rng = exposures.get("recoverable_range_sar")
    if isinstance(rng, dict):
        low = rng.get("low")
        high = rng.get("high")
        try:
            low_v = None if low is None else float(low)
        except (TypeError, ValueError):
            low_v = None
        try:
            high_v = None if high is None else float(high)
        except (TypeError, ValueError):
            high_v = None
        if isinstance(low, dict):
            low_v = low.get("value")
        if isinstance(high, dict):
            high_v = high.get("value")
        return low_v, high_v
    return None, None


def _exposure_basis(context: BusinessContext, signal: Signal) -> tuple[Optional[float], str]:
    """The monetary base an impact is computed from, plus its formula.

    Returns ``(base, formula)``; ``base is None`` means the required Orbit metric
    is unavailable and NO impact may be quantified.
    """
    # Prefer Orbit's explicit recoverable range.
    low, high = _recoverable_range(context)
    if high is not None and high > 0:
        return high, "Orbit recoverable_range_sar.high (upper bound of recoverable value)"

    capital = _exposure(context, "capital_exposed_sar")
    if capital is not None and capital > 0 and signal.domain == "inventory":
        return capital, "Orbit exposures.capital_exposed_sar (capital tied up in inventory)"

    gpar = _exposure(context, "gross_profit_at_risk_sar")
    if gpar is not None and gpar > 0 and signal.domain in {"margin", "financial", "sales", "procurement"}:
        return gpar, "Orbit exposures.gross_profit_at_risk_sar (profit at risk)"

    if capital is not None and capital > 0:
        return capital, "Orbit exposures.capital_exposed_sar (capital exposed)"

    return None, "no monetary Orbit exposure available for this domain"


def quantify_signal(
    context: BusinessContext,
    signal: Signal,
    causes: Optional[list[RootCause]] = None,
) -> Optional[ImpactEstimate]:
    """Quantify POTENTIAL and EXPECTED impact for one signal.

    Returns ``None`` when the data required to quantify impact is unavailable —
    an unquantified signal is correct behaviour, not a failure.
    """
    base, base_formula = _exposure_basis(context, signal)
    if base is None or base <= 0:
        return None

    causes = causes or []
    for cause in causes:
        if cause.signal_id != signal.signal_id:
            continue
        fraction = RECOVERABLE_FRACTION_BY_CAUSE.get(cause.cause_type)
        if fraction is None:
            continue
        discount = SUPPORT_DISCOUNT.get(cause.support_level, 0.0)
        if discount <= 0:
            continue

        potential = base * fraction * discount
        if potential < MIN_IMMATERIAL_SAR:
            continue

        expected = potential * (1.0 - EXPECTED_UPLIFT)
        formula = (
            f"{base_formula} × recoverable_fraction({cause.cause_type}={fraction:.2f}) "
            f"× evidence_discount({cause.support_level.value}={discount:.2f})"
        )
        assumptions = [
            f"recoverable_fraction({cause.cause_type}) = {fraction:.2f}",
            f"evidence_discount({cause.support_level.value}) = {discount:.2f}",
            f"expected = potential × {1 - EXPECTED_UPLIFT:.2f} (execution uncertainty)",
            "no execution, approval or verification is implied by this estimate",
        ]
        evidence = sorted(set(list(signal.evidence_ids) + list(cause.evidence_ids)))

        return ImpactEstimate(
            signal_id=signal.signal_id,
            kind=ImpactKind.POTENTIAL,
            amount_sar=round(potential, 2),
            lower_bound_sar=round(potential * 0.5, 2),
            upper_bound_sar=round(potential * 1.5, 2),
            formula=formula,
            assumptions=assumptions,
            confidence=round(min(0.9, cause.confidence * discount), 4),
            evidence_ids=evidence,
            currency="SAR",
            period=(
                f"{context.state_version}"
            ),
            calculation_version=IMPACT_CALCULATION_VERSION,
        )

    # No cause with a usable fraction: fall back to a conservative, honest estimate
    # ONLY if Orbit gave an explicit recoverable range. If every candidate cause is
    # UNKNOWN support, we have no defensible causal basis and must not quantify a
    # headline number — return None.
    low, high = _recoverable_range(context)
    if high is None or high <= 0:
        return None
    if causes and all(
        c.support_level is RootCauseSupportLevel.UNKNOWN for c in causes
    ):
        return None
    potential = high
    if potential < MIN_IMMATERIAL_SAR:
        return None
    return ImpactEstimate(
        signal_id=signal.signal_id,
        kind=ImpactKind.POTENTIAL,
        amount_sar=round(potential, 2),
        lower_bound_sar=round(low if low is not None else potential * 0.5, 2),
        upper_bound_sar=round(potential, 2),
        formula="Orbit recoverable_range_sar.high (no cause-specific fraction available)",
        assumptions=[
            "no cause-specific recoverable fraction applied",
            "no execution, approval or verification is implied by this estimate",
        ],
        confidence=0.4,
        evidence_ids=list(signal.evidence_ids),
        currency="SAR",
        period=context.state_version,
        calculation_version=IMPACT_CALCULATION_VERSION,
    )


def expected_from_potential(potential: ImpactEstimate) -> ImpactEstimate:
    """Derive the EXPECTED impact from a POTENTIAL estimate.

    Kept as a separate kind so the two are never conflated.
    """
    amount = round(potential.amount_sar * (1.0 - EXPECTED_UPLIFT), 2)
    return ImpactEstimate(
        impact_id=potential.impact_id,
        signal_id=potential.signal_id,
        kind=ImpactKind.EXPECTED,
        amount_sar=amount,
        lower_bound_sar=round(potential.lower_bound_sar * (1.0 - EXPECTED_UPLIFT), 2),
        upper_bound_sar=round(potential.upper_bound_sar * (1.0 - EXPECTED_UPLIFT), 2),
        formula=f"potential × {1 - EXPECTED_UPLIFT:.2f}",
        assumptions=potential.assumptions
        + [
            "expected is a planning figure; it is neither approved, executed nor verified",
        ],
        confidence=round(potential.confidence * 0.8, 4),
        evidence_ids=potential.evidence_ids,
        currency=potential.currency,
        period=potential.period,
        calculation_version=IMPACT_CALCULATION_VERSION,
    )


def quantify(
    context: BusinessContext,
    signals: list[Signal],
    causes: list[RootCause],
) -> list[ImpactEstimate]:
    """Quantify impact across all signals, emitting both POTENTIAL and EXPECTED."""
    estimates: list[ImpactEstimate] = []
    for signal in signals:
        potential = quantify_signal(context, signal, causes)
        if potential is None:
            continue
        estimates.append(potential)
        estimates.append(expected_from_potential(potential))
    return estimates


def potentials_by_signal(estimates: list[ImpactEstimate]) -> dict[Any, ImpactEstimate]:
    """Index POTENTIAL estimates by signal id (last wins)."""
    return {
        e.signal_id: e for e in estimates if e.kind is ImpactKind.POTENTIAL
    }


def expected_by_signal(estimates: list[ImpactEstimate]) -> dict[Any, ImpactEstimate]:
    """Index EXPECTED estimates by signal id (last wins)."""
    return {
        e.signal_id: e for e in estimates if e.kind is ImpactKind.EXPECTED
    }

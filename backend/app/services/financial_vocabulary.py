"""Canonical financial vocabulary (Phase B, WS3).

Single source of truth for monetary field names and the alias map that
historical/peripheral modules use.  Every monetary value is expressed in SAR
and rounded to 2 decimals (see FINANCIAL_VOCABULARY_ADR.md).

Canonical names:
    inventory_value_sar, capital_at_risk_sar, revenue_at_risk_sar,
    gross_profit_at_risk_sar, recoverable_low_sar, recoverable_high_sar,
    expected_recovery_sar, actual_recovery_sar

The ``ALIAS_MAP`` below documents every known drift alias and what canonical
name it maps to.  ``canonicalize()`` rewrites an arbitrary dict so downstream
consumers (ai_response_validator._collect_evidence_sar_values, evidence
packaging, reports) can rely on canonical keys only.
"""
from __future__ import annotations

from typing import Any

# ── Canonical keys ──────────────────────────────────────────────────────────
INVENTORY_VALUE_SAR = "inventory_value_sar"
CAPITAL_AT_RISK_SAR = "capital_at_risk_sar"
REVENUE_AT_RISK_SAR = "revenue_at_risk_sar"
GROSS_PROFIT_AT_RISK_SAR = "gross_profit_at_risk_sar"
RECOVERABLE_LOW_SAR = "recoverable_low_sar"
RECOVERABLE_HIGH_SAR = "recoverable_high_sar"
EXPECTED_RECOVERY_SAR = "expected_recovery_sar"
ACTUAL_RECOVERY_SAR = "actual_recovery_sar"

CANONICAL_KEYS: frozenset[str] = frozenset({
    INVENTORY_VALUE_SAR,
    CAPITAL_AT_RISK_SAR,
    REVENUE_AT_RISK_SAR,
    GROSS_PROFIT_AT_RISK_SAR,
    RECOVERABLE_LOW_SAR,
    RECOVERABLE_HIGH_SAR,
    EXPECTED_RECOVERY_SAR,
    ACTUAL_RECOVERY_SAR,
})

# Drift aliases → canonical key (FINANCIAL_VOCABULARY_ADR.md §3, §5.1).
ALIAS_MAP: dict[str, str] = {
    # Recovery-intelligence fields were named without the _sar suffix.
    "recoverable_low": RECOVERABLE_LOW_SAR,
    "recoverable_high": RECOVERABLE_HIGH_SAR,
    "expected_recovery": EXPECTED_RECOVERY_SAR,
    # Money-audit action dicts used "recoverable_value_*" phrasing.
    "recoverable_value_low_sar": RECOVERABLE_LOW_SAR,
    "recoverable_value_high_sar": RECOVERABLE_HIGH_SAR,
    # Legacy DB column name for expected recovery.
    "expected_recovery_sar_v2": EXPECTED_RECOVERY_SAR,
    "capital_at_risk": CAPITAL_AT_RISK_SAR,
}


def canonical_key(name: str) -> str:
    """Return the canonical key for any known (or already canonical) name."""
    if name in CANONICAL_KEYS:
        return name
    return ALIAS_MAP.get(name, name)


def canonicalize(obj: dict[str, Any]) -> dict[str, Any]:
    """Normalize financial keys in ``obj`` to canonical names, in place.

    Non-financial keys are left untouched.  If a canonical key and one of its
    aliases are both present, the canonical key wins and the alias is dropped.
    """
    remap: list[tuple[str, str]] = []
    for key, value in list(obj.items()):
        target = canonical_key(key)
        if target != key:
            remap.append((key, target))
    for alias, target in remap:
        if target not in obj and alias in obj:
            obj[target] = obj.pop(alias)
        else:
            obj.pop(alias, None)
    return obj
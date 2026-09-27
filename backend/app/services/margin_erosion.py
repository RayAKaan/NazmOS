"""Canonical margin erosion band (Batch 3: pricing.margin_erosion_risk).

Deterministic target = the canonical gross-margin RATIO
(``audit_core.gross_margin_pct``, (sell-cost)/sell, 0 when sell <= 0). Bands
mirror the threshold set the codebase actually enforces:

    < 0.15   -> LOW    (margin_agent floor / MARGIN_EROSION triage floor,
                        evidence_package triage_reason)
    <= 0.40  -> MEDIUM (privacy_firewall._band_margin ceiling; the leakage
                        target ``TARGET_MARGIN_PCT = 0.22`` is cited in prompts,
                        not a band edge)
    > 0.40   -> HIGH

The band name is margin MAGNITUDE, not a risk level: a LOW band means the
lowest margin -- i.e. the MOST eroded. Jev may only score within these three
rungs (shadow mode).
"""
from __future__ import annotations

from decimal import Decimal

from app.orchestration.contracts import MARGIN_EROSION_BANDS

_MARGIN_FLOOR = Decimal("0.15")
_MARGIN_CEILING = Decimal("0.40")


def margin_erosion_band(margin_ratio: int | float | Decimal | None) -> str:
    """Deterministic erosion band over the canonical gross-margin ratio."""
    if margin_ratio is None:
        return "LOW"
    ratio = Decimal(str(margin_ratio))
    if ratio < _MARGIN_FLOOR:
        return "LOW"
    if ratio <= _MARGIN_CEILING:
        return "MEDIUM"
    return "HIGH"
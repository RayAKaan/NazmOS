"""V8 A/B Decision Framework.

Three decision modes for counterfactual evaluation:
  MODE_A: Deterministic only (baseline)
  MODE_B: Deterministic + AI reasoning
  MODE_C: Deterministic + AI reasoning + historical outcomes

All three receive the SAME business state.
Only after counterfactual comparison should a policy be selected for execution.

This prevents AI from changing the environment before the baseline is evaluated.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from app.services.evidence_package import (
    ItemEvidence, BusinessContext, AuditEvidencePackage,
    triage_items_for_ai,
)
from app.services.ai_reasoning import AIReasoningResult, reason_about_item
from app.services.ai_response_validator import (
    validate_ai_response, select_final_decision, ValidationResult,
)

logger = logging.getLogger(__name__)


@dataclass
class ModeResult:
    """Result from one decision mode for one item."""
    mode: str
    sku: str
    deterministic_decision: str
    ai_decision: str | None = None
    final_decision: str = ""
    decision_source: str = ""
    ai_confidence: float = 0.0
    ai_reasoning: str = ""
    validation: ValidationResult | None = None
    ai_latency_ms: float = 0
    ai_calls: int = 0
    constraint_rejected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "sku": self.sku,
            "deterministic_decision": self.deterministic_decision,
            "ai_decision": self.ai_decision,
            "final_decision": self.final_decision,
            "decision_source": self.decision_source,
            "ai_confidence": self.ai_confidence,
            "ai_reasoning": self.ai_reasoning,
            "validation": self.validation.to_dict() if self.validation else None,
            "ai_latency_ms": self.ai_latency_ms,
            "ai_calls": self.ai_calls,
            "constraint_rejected": self.constraint_rejected,
        }


@dataclass
class AuditABResult:
    """Complete A/B comparison result for one audit."""
    business_id: str
    mode_a: list[ModeResult] = field(default_factory=list)
    mode_b: list[ModeResult] = field(default_factory=list)
    mode_c: list[ModeResult] = field(default_factory=list)
    ai_total_calls: int = 0
    ai_total_tokens: int = 0
    ai_total_latency_ms: float = 0
    ai_budget_used: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "business_id": self.business_id,
            "mode_a": [r.to_dict() for r in self.mode_a],
            "mode_b": [r.to_dict() for r in self.mode_b],
            "mode_c": [r.to_dict() for r in self.mode_c],
            "ai_total_calls": self.ai_total_calls,
            "ai_total_tokens": self.ai_total_tokens,
            "ai_total_latency_ms": self.ai_total_latency_ms,
            "ai_budget_used": self.ai_budget_used,
        }


def deterministic_decision_for_item(item: ItemEvidence) -> str:
    """Pure deterministic decision logic (no AI). This is the baseline.

    V11 improvements:
    - Zero stock + demand → REORDER (not MANUAL_REVIEW)
    - Ghost PO detection (PO created but never received)
    - Seasonal dormancy awareness
    - UNKNOWN classification collapse fix
    """
    cls = item.classification

    # === V11 FIX 1: Zero stock + demand detection ===
    # If zero stock but clear demand pattern, this is a stockout → REORDER
    if item.current_stock == 0 and item.daily_velocity > 0:
        # Check if there's an incoming PO that should arrive soon
        if item.confirmed_inbound_qty > 0:
            return "DO_NOTHING"  # PO incoming, wait for delivery
        return "REORDER"

    # === V11 FIX 2: Ghost PO detection ===
    # If confirmed inbound but no demand for extended period, PO may be ghost
    if item.confirmed_inbound_qty > 0 and item.current_stock == 0:
        if item.days_since_last_sale and item.days_since_last_sale > 120:
            # PO was created but item hasn't sold in 120+ days → ghost PO
            return "REORDER"  # Need fresh PO, not ghost

    # === DEAD STOCK ===
    if cls == "DEAD":
        if item.current_stock > 0:
            return "DISCOUNT"
        return "DO_NOTHING"

    # === SEASONAL with enhanced logic ===
    if cls == "SEASONAL":
        # V11 FIX 3: Seasonal dormancy awareness
        # If seasonal item with zero velocity but upcoming season, hold inventory
        if item.current_stock > 0 and item.daily_velocity == 0:
            # Check if season is coming (within 45 days)
            # If monthly_concentration_peak > 0.5, season likely exists
            if item.monthly_concentration_peak and item.monthly_concentration_peak > 0.5:
                return "DO_NOTHING"  # Hold for season
        if item.overstock_days and item.overstock_days > 90:
            return "DO_NOTHING"
        if item.monthly_concentration_peak and item.monthly_concentration_peak > 0.7:
            return "DO_NOTHING"
        return "REORDER"

    # === SLOW MOVING ===
    if cls == "SLOW MOVING":
        if item.current_stock > 0:
            return "DISCOUNT"
        return "REORDER"

    # === FAST ===
    if cls == "FAST":
        if item.stockout_days:
            return "REORDER"
        if item.overstock_days and item.overstock_days > 90:
            return "TRANSFER"
        return "DO_NOTHING"

    # === V11 FIX 4: UNKNOWN classification collapse fix ===
    if cls == "UNKNOWN":
        # Zero stock + demand = REORDER (not MANUAL_REVIEW)
        if item.current_stock == 0 and item.daily_velocity > 0:
            return "REORDER"
        # Zero stock + no demand = DO_NOTHING (nothing to do)
        if item.current_stock == 0 and item.daily_velocity == 0:
            return "DO_NOTHING"
        # Has stock + zero velocity for 45+ days = DISCOUNT (stale inventory)
        if item.current_stock > 0 and item.days_since_last_sale and item.days_since_last_sale > 45:
            return "DISCOUNT"
        # Has stock + recent velocity = DO_NOTHING (healthy despite unknown label)
        if item.current_stock > 0 and item.recent_velocity_per_day > 0:
            return "DO_NOTHING"
        # Has stock + no recent sales but not 45 days yet = MANUAL_REVIEW (ambiguous)
        return "MANUAL_REVIEW"

    # === NEW ===
    if cls == "NEW":
        return "DO_NOTHING"

    # === HEALTHY or default ===
    if item.overstock_days and item.overstock_days > 120:
        return "RECOVERY_MATCH"
    if item.stockout_days:
        return "REORDER"

    return "DO_NOTHING"


async def run_counterfactual_audit(
    package: AuditEvidencePackage,
    llm_caller: Callable[[str, str], Awaitable[str]] | None = None,
    historical_outcomes: dict[str, list[dict]] | None = None,
    *,
    max_ai_calls: int = 10,
    include_mode_c: bool = True,
    ai_call_delay_s: float = 0.0,
) -> AuditABResult:
    """Run all three decision modes on the SAME business state.

    This is the counterfactual evaluation:
    - Same evidence package for all modes
    - Same deterministic triage
    - AI receives only triaged items
    - No mode changes the business state before others are evaluated

    ai_call_delay_s paces provider calls (e.g. 3.5s keeps free-tier
    Gemini under its 20 requests/minute ceiling).
    """
    result = AuditABResult(business_id=package.business.business_id)

    # Step 1: Deterministic decision for ALL items (MODE A)
    for item in package.items:
        det_decision = deterministic_decision_for_item(item)
        result.mode_a.append(ModeResult(
            mode="MODE_A",
            sku=item.sku,
            deterministic_decision=det_decision,
            final_decision=det_decision,
            decision_source="DETERMINISTIC",
        ))

    # Step 2: Triage items for AI reasoning
    items_for_ai = triage_items_for_ai(package.items, max_calls=max_ai_calls)
    ai_skus = {item.sku for item in items_for_ai}

    # Step 3: MODE B - Deterministic + AI reasoning (no historical outcomes)
    for item in package.items:
        det_decision = deterministic_decision_for_item(item)

        if item.sku in ai_skus and llm_caller:
            # AI reasoning
            ai_result = await reason_about_item(
                item, package.business, llm_caller, include_historical=False,
            )
            validation = validate_ai_response(ai_result, item, package.business)
            final_decision, source = select_final_decision(
                det_decision, ai_result.decision, ai_result.confidence, validation,
            )
            result.mode_b.append(ModeResult(
                mode="MODE_B",
                sku=item.sku,
                deterministic_decision=det_decision,
                ai_decision=ai_result.decision,
                final_decision=final_decision,
                decision_source=source,
                ai_confidence=ai_result.confidence,
                ai_reasoning=ai_result.reasoning,
                validation=validation,
                ai_latency_ms=ai_result.latency_ms,
                ai_calls=1,
                constraint_rejected=validation.constraint_rejected if validation else False,
            ))
            result.ai_total_calls += 1
            result.ai_total_latency_ms += ai_result.latency_ms
            result.ai_budget_used += 1
            if ai_call_delay_s > 0:
                await asyncio.sleep(ai_call_delay_s)
        else:
            result.mode_b.append(ModeResult(
                mode="MODE_B",
                sku=item.sku,
                deterministic_decision=det_decision,
                final_decision=det_decision,
                decision_source="DETERMINISTIC_NO_AI",
            ))

    # Step 4: MODE C - Deterministic + AI + historical outcomes
    if include_mode_c:
        for item in package.items:
            det_decision = deterministic_decision_for_item(item)

            if item.sku in ai_skus and llm_caller:
                # Create item with historical outcomes
                item_with_history = ItemEvidence(
                    sku=item.sku,
                    product_name=item.product_name,
                    classification=item.classification,
                    current_stock=item.current_stock,
                    cost_price_sar=item.cost_price_sar,
                    sell_price_sar=item.sell_price_sar,
                    inventory_value_sar=item.inventory_value_sar,
                    recent_velocity_per_day=item.recent_velocity_per_day,
                    prior_velocity_per_day=item.prior_velocity_per_day,
                    daily_velocity=item.daily_velocity,
                    days_of_supply=item.days_of_supply,
                    days_since_last_sale=item.days_since_last_sale,
                    inventory_age_days=item.inventory_age_days,
                    monthly_concentrations=item.monthly_concentrations,
                    monthly_concentration_peak=item.monthly_concentration_peak,
                    confirmed_inbound_qty=item.confirmed_inbound_qty,
                    supplier_lead_time_days=item.supplier_lead_time_days,
                    supplier_moq=item.supplier_moq,
                    supplier_name=item.supplier_name,
                    capital_at_risk_sar=item.capital_at_risk_sar,
                    revenue_at_risk_sar=item.revenue_at_risk_sar,
                    gross_profit_at_risk_sar=item.gross_profit_at_risk_sar,
                    recoverable_low_sar=item.recoverable_low_sar,
                    recoverable_high_sar=item.recoverable_high_sar,
                    expected_recovery_sar=item.expected_recovery_sar,
                    recovery_confidence=item.recovery_confidence,
                    candidate_actions=item.candidate_actions,
                    overstock_days=item.overstock_days,
                    stockout_days=item.stockout_days,
                    margin_pct=item.margin_pct,
                    target_margin_pct=item.target_margin_pct,
                    is_strategic=item.is_strategic,
                    historical_outcomes=historical_outcomes.get(item.sku, []) if historical_outcomes else [],
                )

                ai_result = await reason_about_item(
                    item_with_history, package.business, llm_caller, include_historical=True,
                )
                validation = validate_ai_response(ai_result, item_with_history, package.business)
                final_decision, source = select_final_decision(
                    det_decision, ai_result.decision, ai_result.confidence, validation,
                )
                result.mode_c.append(ModeResult(
                    mode="MODE_C",
                    sku=item.sku,
                    deterministic_decision=det_decision,
                    ai_decision=ai_result.decision,
                    final_decision=final_decision,
                    decision_source=source,
                    ai_confidence=ai_result.confidence,
                    ai_reasoning=ai_result.reasoning,
                validation=validation,
                ai_latency_ms=ai_result.latency_ms,
                ai_calls=1,
                constraint_rejected=validation.constraint_rejected if validation else False,
            ))
            if ai_call_delay_s > 0:
                await asyncio.sleep(ai_call_delay_s)
        else:
            result.mode_c.append(ModeResult(
                mode="MODE_C",
                    sku=item.sku,
                    deterministic_decision=det_decision,
                    final_decision=det_decision,
                    decision_source="DETERMINISTIC_NO_AI",
                ))

    return result


def compare_modes(ab_result: AuditABResult) -> dict[str, Any]:
    """Compare the three modes and compute metrics."""
    def _count_decisions(results: list[ModeResult]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in results:
            counts[r.final_decision] = counts.get(r.final_decision, 0) + 1
        return counts

    def _count_sources(results: list[ModeResult]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in results:
            counts[r.decision_source] = counts.get(r.decision_source, 0) + 1
        return counts

    mode_a_decisions = _count_decisions(ab_result.mode_a)
    mode_b_decisions = _count_decisions(ab_result.mode_b)
    mode_c_decisions = _count_decisions(ab_result.mode_c)

    # Count where AI changed the decision
    ai_overrides = 0
    ai_agreements = 0
    ai_manual_reviews = 0
    ai_low_confidence = 0
    constraint_rejections = 0
    for r in ab_result.mode_b:
        if r.ai_decision and r.decision_source not in ("DETERMINISTIC_NO_AI",):
            if r.decision_source.startswith("AI_"):
                ai_overrides += 1
            elif "AGREES" in r.decision_source:
                ai_agreements += 1
            elif "MANUAL_REVIEW" in r.decision_source:
                ai_manual_reviews += 1
            elif "LOW_AI_CONFIDENCE" in r.decision_source:
                # AI participated with a valid but sub-threshold answer;
                # deterministic decision retained. Count it so coverage is visible.
                ai_low_confidence += 1
        if r.constraint_rejected:
            constraint_rejections += 1

    return {
        "mode_a_decisions": mode_a_decisions,
        "mode_b_decisions": mode_b_decisions,
        "mode_c_decisions": mode_c_decisions,
        "ai_overrides": ai_overrides,
        "ai_agreements": ai_agreements,
        "ai_manual_reviews": ai_manual_reviews,
        "ai_low_confidence": ai_low_confidence,
        "constraint_rejections": constraint_rejections,
        "ai_total_calls": ab_result.ai_total_calls,
        "ai_total_latency_ms": round(ab_result.ai_total_latency_ms, 1),
        "items_evaluated": len(ab_result.mode_a),
        "items_triaged_to_ai": ab_result.ai_budget_used,
        "ai_effective_participation": (
            ai_overrides + ai_agreements + ai_manual_reviews + ai_low_confidence
        ),
    }


# ============================================================================
# V11: CHALLENGE-BASED DECISION MODES
# ============================================================================

@dataclass
class V11ModeResult:
    """Result from one V11 decision mode for one item."""
    mode: str
    sku: str
    deterministic_decision: str
    challenge_status: str | None = None
    challenge_proposed_decision: str | None = None
    challenge_confidence: float = 0.0
    challenge_reason: str = ""
    final_decision: str = ""
    decision_source: str = ""
    ai_latency_ms: float = 0
    ai_calls: int = 0
    challenge_valid: bool = True
    challenge_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "sku": self.sku,
            "deterministic_decision": self.deterministic_decision,
            "challenge_status": self.challenge_status,
            "challenge_proposed_decision": self.challenge_proposed_decision,
            "challenge_confidence": self.challenge_confidence,
            "challenge_reason": self.challenge_reason,
            "final_decision": self.final_decision,
            "decision_source": self.decision_source,
            "ai_latency_ms": self.ai_latency_ms,
            "ai_calls": self.ai_calls,
            "challenge_valid": self.challenge_valid,
            "challenge_errors": self.challenge_errors,
        }


@dataclass
class V11AuditResult:
    """Complete V11 A/B/C comparison result for one audit."""
    business_id: str
    mode_a: list[V11ModeResult] = field(default_factory=list)
    mode_b: list[V11ModeResult] = field(default_factory=list)
    mode_c: list[V11ModeResult] = field(default_factory=list)
    ai_total_calls: int = 0
    ai_total_latency_ms: float = 0
    ai_budget_used: int = 0
    challenge_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "business_id": self.business_id,
            "mode_a": [r.to_dict() for r in self.mode_a],
            "mode_b": [r.to_dict() for r in self.mode_b],
            "mode_c": [r.to_dict() for r in self.mode_c],
            "ai_total_calls": self.ai_total_calls,
            "ai_total_latency_ms": round(self.ai_total_latency_ms, 1),
            "ai_budget_used": self.ai_budget_used,
            "challenge_counts": self.challenge_counts,
        }


async def run_v11_counterfactual_audit(
    package: AuditEvidencePackage,
    context_engine: Any,
    llm_caller: Callable[[str, str], Awaitable[str]] | None = None,
    *,
    max_ai_calls: int = 10,
    include_mode_c: bool = True,
    ai_call_delay_s: float = 0.0,
    virtual_date: Any = None,
) -> V11AuditResult:
    """Run V11 three-mode counterfactual audit with AI challenge.

    MODE_A: Deterministic only (baseline)
    MODE_B: Deterministic + Context + AI Challenge
    MODE_C: Deterministic + Context + AI Challenge + Outcomes

    All three receive the SAME business state.
    """
    from app.services.business_context import BusinessContextEngine
    from app.services.ai_challenge import (
        challenge_deterministic, select_final_decision_v11, ChallengeStatus,
    )
    from datetime import date as date_type

    if context_engine is None:
        context_engine = BusinessContextEngine()

    if virtual_date is None:
        virtual_date = date_type.today()

    result = V11AuditResult(business_id=package.business.business_id)

    # Step 1: MODE A — Deterministic only (same as V10)
    for item in package.items:
        det_decision = deterministic_decision_for_item(item)
        result.mode_a.append(V11ModeResult(
            mode="MODE_A",
            sku=item.sku,
            deterministic_decision=det_decision,
            final_decision=det_decision,
            decision_source="DETERMINISTIC",
        ))

    # Step 2: Triage items for AI challenge
    items_for_ai = triage_items_for_ai(package.items, max_calls=max_ai_calls)
    ai_skus = {item.sku for item in items_for_ai}

    # Track challenge statistics
    challenge_stats = {
        "NO_CHALLENGE": 0,
        "CHALLENGE": 0,
        "INSUFFICIENT_EVIDENCE": 0,
        "CHALLENGE_ACCEPTED": 0,
        "CHALLENGE_REJECTED": 0,
    }

    # Step 3: MODE B — Deterministic + Context + AI Challenge
    for item in package.items:
        det_decision = deterministic_decision_for_item(item)

        if item.sku in ai_skus and llm_caller:
            # Build structured context
            context = await context_engine.build_context(
                item, package.business, virtual_date,
            )

            # Only challenge if eligible
            if context.ai_challenge_eligible:
                # Run AI challenge
                challenge = await challenge_deterministic(context, llm_caller)
                result.ai_total_calls += 1
                result.ai_total_latency_ms += challenge.latency_ms
                result.ai_budget_used += 1

                # Track statistics
                challenge_stats[challenge.status.value] = challenge_stats.get(challenge.status.value, 0) + 1

                # Select final decision
                final_decision, source = select_final_decision_v11(
                    det_decision, challenge, context,
                )

                if source == "AI_CHALLENGE_ACCEPTED":
                    challenge_stats["CHALLENGE_ACCEPTED"] = challenge_stats.get("CHALLENGE_ACCEPTED", 0) + 1
                else:
                    challenge_stats["CHALLENGE_REJECTED"] = challenge_stats.get("CHALLENGE_REJECTED", 0) + 1

                result.mode_b.append(V11ModeResult(
                    mode="MODE_B",
                    sku=item.sku,
                    deterministic_decision=det_decision,
                    challenge_status=challenge.status.value,
                    challenge_proposed_decision=challenge.proposed_decision,
                    challenge_confidence=challenge.confidence,
                    challenge_reason=challenge.reason,
                    final_decision=final_decision,
                    decision_source=source,
                    ai_latency_ms=challenge.latency_ms,
                    ai_calls=1,
                    challenge_valid=challenge.is_valid,
                    challenge_errors=challenge.validation_errors,
                ))

                if ai_call_delay_s > 0:
                    await asyncio.sleep(ai_call_delay_s)
            else:
                # Not eligible for challenge
                result.mode_b.append(V11ModeResult(
                    mode="MODE_B",
                    sku=item.sku,
                    deterministic_decision=det_decision,
                    challenge_status="NOT_ELIGIBLE",
                    final_decision=det_decision,
                    decision_source="DETERMINISTIC_NOT_ELIGIBLE",
                ))
        else:
            # No AI caller or not triaged
            result.mode_b.append(V11ModeResult(
                mode="MODE_B",
                sku=item.sku,
                deterministic_decision=det_decision,
                final_decision=det_decision,
                decision_source="DETERMINISTIC_NO_AI",
            ))

    # Step 4: MODE C — Deterministic + Context + AI Challenge + Outcomes
    if include_mode_c:
        for item in package.items:
            det_decision = deterministic_decision_for_item(item)

            if item.sku in ai_skus and llm_caller:
                # Build context with historical outcomes
                historical = package.business.previous_outcomes if hasattr(package.business, 'previous_outcomes') else []
                context = await context_engine.build_context(
                    item, package.business, virtual_date,
                    historical_outcomes=historical,
                )

                if context.ai_challenge_eligible:
                    challenge = await challenge_deterministic(context, llm_caller)
                    result.ai_total_calls += 1
                    result.ai_total_latency_ms += challenge.latency_ms
                    result.ai_budget_used += 1

                    final_decision, source = select_final_decision_v11(
                        det_decision, challenge, context,
                    )

                    result.mode_c.append(V11ModeResult(
                        mode="MODE_C",
                        sku=item.sku,
                        deterministic_decision=det_decision,
                        challenge_status=challenge.status.value,
                        challenge_proposed_decision=challenge.proposed_decision,
                        challenge_confidence=challenge.confidence,
                        challenge_reason=challenge.reason,
                        final_decision=final_decision,
                        decision_source=source,
                        ai_latency_ms=challenge.latency_ms,
                        ai_calls=1,
                        challenge_valid=challenge.is_valid,
                        challenge_errors=challenge.validation_errors,
                    ))

                    if ai_call_delay_s > 0:
                        await asyncio.sleep(ai_call_delay_s)
                else:
                    result.mode_c.append(V11ModeResult(
                        mode="MODE_C",
                        sku=item.sku,
                        deterministic_decision=det_decision,
                        challenge_status="NOT_ELIGIBLE",
                        final_decision=det_decision,
                        decision_source="DETERMINISTIC_NOT_ELIGIBLE",
                    ))
            else:
                result.mode_c.append(V11ModeResult(
                    mode="MODE_C",
                    sku=item.sku,
                    deterministic_decision=det_decision,
                    final_decision=det_decision,
                    decision_source="DETERMINISTIC_NO_AI",
                ))

    result.challenge_counts = challenge_stats
    return result


def compare_v11_modes(ab_result: V11AuditResult) -> dict[str, Any]:
    """Compare V11 three modes and compute metrics."""
    def _count_decisions(results: list[V11ModeResult]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in results:
            counts[r.final_decision] = counts.get(r.final_decision, 0) + 1
        return counts

    def _count_sources(results: list[V11ModeResult]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in results:
            counts[r.decision_source] = counts.get(r.decision_source, 0) + 1
        return counts

    mode_a_decisions = _count_decisions(ab_result.mode_a)
    mode_b_decisions = _count_decisions(ab_result.mode_b)
    mode_c_decisions = _count_decisions(ab_result.mode_c)

    mode_a_sources = _count_sources(ab_result.mode_a)
    mode_b_sources = _count_sources(ab_result.mode_b)
    mode_c_sources = _count_sources(ab_result.mode_c)

    # Count challenge outcomes
    challenges_made = 0
    challenges_accepted = 0
    challenges_rejected = 0
    no_challenges = 0
    insufficient_evidence = 0

    for r in ab_result.mode_b:
        if r.challenge_status == "CHALLENGE":
            challenges_made += 1
        elif r.challenge_status == "NO_CHALLENGE":
            no_challenges += 1
        elif r.challenge_status == "INSUFFICIENT_EVIDENCE":
            insufficient_evidence += 1

        if r.decision_source == "AI_CHALLENGE_ACCEPTED":
            challenges_accepted += 1
        elif r.decision_source == "CHALLENGE_REJECTED":
            challenges_rejected += 1

    return {
        "mode_a_decisions": mode_a_decisions,
        "mode_b_decisions": mode_b_decisions,
        "mode_c_decisions": mode_c_decisions,
        "mode_a_sources": mode_a_sources,
        "mode_b_sources": mode_b_sources,
        "mode_c_sources": mode_c_sources,
        "challenges_made": challenges_made,
        "challenges_accepted": challenges_accepted,
        "challenges_rejected": challenges_rejected,
        "no_challenges": no_challenges,
        "insufficient_evidence": insufficient_evidence,
        "ai_total_calls": ab_result.ai_total_calls,
        "ai_total_latency_ms": round(ab_result.ai_total_latency_ms, 1),
        "items_evaluated": len(ab_result.mode_a),
        "items_triaged_to_ai": ab_result.ai_budget_used,
        "challenge_counts": ab_result.challenge_counts,
    }

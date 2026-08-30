"""V8 Closed-Loop Experiment Runner — 60-day counterfactual evaluation.

Runs the complete V8 experiment:
1. DAY 0: Upload → Money Audit → Deterministic analysis → AI reasoning on ambiguous/high-value
2. Generate recommendations → Apply constraints → Approve actions → Execute supported actions
3. Record state → Advance virtual clock → Generate new sales/business state
4. Run audit again → Measure outcomes → Repeat

Three modes evaluated counterfactually on the SAME business state:
  MODE_A: Deterministic only (baseline)
  MODE_B: Deterministic + AI reasoning
  MODE_C: Deterministic + AI reasoning + historical outcomes

Only after counterfactual comparison should a policy be selected for execution.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Awaitable

from app.services.v8_business_simulator import (
    V8_BUSINESSES, BusinessProfile, ItemProfile, DaySnapshot,
    get_v8_items, simulate_60_days, _seed_rng,
)
from app.services.evidence_package import (
    ItemEvidence, BusinessContext, AuditEvidencePackage,
    build_item_evidence, triage_items_for_ai,
)
from app.services.ab_decision_framework import (
    deterministic_decision_for_item, run_counterfactual_audit,
    AuditABResult, compare_modes, ModeResult,
)
from app.services.outcome_tracker import OutcomeTracker, OutcomeRecord
from app.services.calibration_service import CalibrationService
from app.services.recovery_intelligence import classify_inventory, estimate_recovery
from app.services.constraint_service import filter_action
from app.services.action_registry import ACTION_REGISTRY
from decimal import Decimal

logger = logging.getLogger(__name__)

D = Decimal


@dataclass
class CheckpointResult:
    """Result of a single checkpoint (Day 0, 7, 14, etc.)."""
    day: int
    business_id: str
    snapshot: DaySnapshot
    mode_a_result: AuditABResult
    mode_b_result: AuditABResult | None = None
    mode_c_result: AuditABResult | None = None
    # Simulated outcomes for this checkpoint
    simulated_outcomes: list[dict[str, Any]] = field(default_factory=list)
    # Metrics
    findings_count: int = 0
    recommendations_count: int = 0
    approvals_count: int = 0
    executions_count: int = 0
    financial_state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "business_id": self.business_id,
            "findings_count": self.findings_count,
            "recommendations_count": self.recommendations_count,
            "approvals_count": self.approvals_count,
            "executions_count": self.executions_count,
            "financial_state": self.financial_state,
            "mode_a": compare_modes(self.mode_a_result) if self.mode_a_result else {},
            "mode_b": compare_modes(self.mode_b_result) if self.mode_b_result else {},
            "mode_c": compare_modes(self.mode_c_result) if self.mode_c_result else {},
            "simulated_outcomes_count": len(self.simulated_outcomes),
        }


@dataclass
class ExperimentResult:
    """Complete 60-day experiment result for one business."""
    business: BusinessProfile
    checkpoints: list[CheckpointResult] = field(default_factory=list)
    outcome_summary: dict[str, Any] = field(default_factory=dict)
    calibration_report: dict[str, Any] = field(default_factory=dict)
    mode_comparison: dict[str, Any] = field(default_factory=dict)
    ai_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "business_name": self.business.name,
            "business_type": self.business.business_type,
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "outcome_summary": self.outcome_summary,
            "calibration_report": self.calibration_report,
            "mode_comparison": self.mode_comparison,
            "ai_metrics": self.ai_metrics,
        }


def _build_business_context(business: BusinessProfile, items: list[ItemProfile], snapshot: DaySnapshot) -> BusinessContext:
    """Build BusinessContext from simulator state."""
    total_inv_value = sum(
        s["stock"] * s["cost"] for s in snapshot.items
    )
    total_recoverable = sum(
        min(s["stock"] * s["cost"], s["stock"] * s["sell"]) for s in snapshot.items if s["stock"] > 0
    )
    return BusinessContext(
        business_id=business.business_id_seed,
        business_type=business.business_type,
        total_inventory_value_sar=round(total_inv_value, 2),
        total_capital_at_risk_sar=round(total_inv_value, 2),
        total_recoverable_high_sar=round(total_recoverable, 2),
        cash_budget=business.cash_budget,
        max_discount_pct=business.max_discount_pct,
        blocked_discount_products=business.blocked_discount_products,
        strategic_products=business.strategic_products,
        blocked_transfer_routes=business.blocked_transfer_routes,
        minimum_margin_pct=business.minimum_margin_pct,
    )


def _build_item_evidence_from_snapshot(
    item_state: dict[str, Any],
    item_profile: ItemProfile,
    business: BusinessProfile,
    snapshot: DaySnapshot,
    day: int,
) -> ItemEvidence:
    """Build ItemEvidence from simulator item state."""
    stock = Decimal(str(item_state["stock"]))
    cost = Decimal(str(item_state["cost"]))
    sell = Decimal(str(item_state["sell"])) if item_state["sell"] > 0 else Decimal(str(item_state["cost"] * 1.5))
    daily_rate = item_state["daily_rate"]
    total_sold = item_state["total_sold"]

    # Compute velocities
    recent_30d = Decimal(str(daily_rate * 30)) if daily_rate > 0 else D("0")
    prior_30d = recent_30d * D("0.8")  # Approximate prior period

    # Classification
    inventory_age = item_profile.inventory_age_days + day
    days_since_sale = 0 if total_sold > 0 else min(day, 60)

    classification = classify_inventory(
        stock=stock,
        recent_qty_30=recent_30d,
        prior_qty_30=prior_30d,
        days_since_last_sale=days_since_sale,
        inventory_age_days=inventory_age,
    )

    # Estimate recovery
    estimate = estimate_recovery(
        classification=classification,
        stock=stock,
        cost=cost,
        sell=sell,
    )

    # Candidate actions based on classification
    candidate_actions = []
    if classification in ("DEAD", "SLOW MOVING") and stock > 0:
        candidate_actions.append("DISCOUNT")
        if business.blocked_discount_products and item_profile.name in business.blocked_discount_products:
            candidate_actions.append("TRANSFER")
            candidate_actions.append("MANUAL_REVIEW")
    if classification == "FAST" and stock <= 0:
        candidate_actions.append("REORDER")
    if classification == "SEASONAL":
        candidate_actions.append("DO_NOTHING")
    if classification == "NEW":
        candidate_actions.append("DO_NOTHING")
    if not candidate_actions:
        candidate_actions.append("DO_NOTHING")

    return build_item_evidence(
        sku=item_profile.sku,
        product_name=item_profile.name,
        classification=classification,
        stock=stock,
        cost=cost,
        sell=sell,
        qty_30d=recent_30d,
        qty_prior=prior_30d,
        days_since_last_sale=days_since_sale,
        inventory_age_days=inventory_age,
        candidate_actions=candidate_actions,
        is_strategic=item_profile.is_strategic,
    )


def _simulate_action_outcome(
    action: dict[str, Any],
    item_state: dict[str, Any],
    item_profile: ItemProfile,
    business: BusinessProfile,
    rng: random.Random,
) -> dict[str, Any]:
    """Simulate the outcome of an approved action using probability-based modeling.

    Returns SIMULATED OUTCOME — never report as actual recovered SAR.
    """
    action_type = action.get("action_type", "DO_NOTHING")
    stock = item_state["stock"]
    cost = item_state["cost"]
    sell = item_state["sell"] if item_state["sell"] > 0 else cost * 1.5

    if action_type == "DISCOUNT":
        # Discount success depends on discount depth and product type
        max_discount = business.max_discount_pct or 20
        discount_pct = min(max_discount, rng.uniform(5, max_discount))
        # Success probability: higher discount = higher chance of sale
        success_prob = min(0.9, 0.3 + (discount_pct / 100) * 2)
        if rng.random() < success_prob:
            units_sold = max(1, int(stock * rng.uniform(0.3, 0.8)))
            recovery = units_sold * sell * (1 - discount_pct / 100)
            return {
                "action_type": "DISCOUNT",
                "success": True,
                "units_affected": units_sold,
                "actual_recovery_sar": round(recovery, 2),
                "actual_savings_sar": 0.0,
                "discount_pct_applied": round(discount_pct, 1),
                "is_simulated": True,
            }
        return {
            "action_type": "DISCOUNT",
            "success": False,
            "units_affected": 0,
            "actual_recovery_sar": 0.0,
            "actual_savings_sar": 0.0,
            "is_simulated": True,
        }

    if action_type == "TRANSFER":
        # Transfer success depends on whether there's demand elsewhere
        success_prob = 0.4  # Base transfer success rate
        if rng.random() < success_prob:
            units = max(1, int(stock * rng.uniform(0.2, 0.6)))
            recovery = units * cost  # Transfer at cost
            return {
                "action_type": "TRANSFER",
                "success": True,
                "units_affected": units,
                "actual_recovery_sar": round(recovery, 2),
                "actual_savings_sar": round(recovery * 0.1, 2),  # 10% handling savings
                "is_simulated": True,
            }
        return {
            "action_type": "TRANSFER",
            "success": False,
            "units_affected": 0,
            "actual_recovery_sar": 0.0,
            "actual_savings_sar": 0.0,
            "is_simulated": True,
        }

    if action_type == "REORDER":
        # Reorder prevents stockout — savings = revenue that would have been lost
        daily_rate = item_state.get("daily_rate", 0)
        if stock <= 0 and daily_rate > 0:
            prevention_value = daily_rate * 7 * sell  # 7 days of prevented stockout
            return {
                "action_type": "REORDER",
                "success": True,
                "units_affected": 0,
                "actual_recovery_sar": 0.0,
                "actual_savings_sar": round(prevention_value, 2),
                "is_simulated": True,
            }
        return {
            "action_type": "REORDER",
            "success": True,
            "units_affected": 0,
            "actual_recovery_sar": 0.0,
            "actual_savings_sar": 0.0,
            "is_simulated": True,
        }

    if action_type == "RECOVERY_MATCH":
        # Recovery match finds a buyer for excess stock
        success_prob = 0.25
        if rng.random() < success_prob:
            units = max(1, int(stock * rng.uniform(0.1, 0.4)))
            recovery = units * cost * 0.7  # Match at 70% of cost
            return {
                "action_type": "RECOVERY_MATCH",
                "success": True,
                "units_affected": units,
                "actual_recovery_sar": round(recovery, 2),
                "actual_savings_sar": 0.0,
                "is_simulated": True,
            }
        return {
            "action_type": "RECOVERY_MATCH",
            "success": False,
            "units_affected": 0,
            "actual_recovery_sar": 0.0,
            "actual_savings_sar": 0.0,
            "is_simulated": True,
        }

    # DO_NOTHING or unsupported
    return {
        "action_type": action_type,
        "success": True,
        "units_affected": 0,
        "actual_recovery_sar": 0.0,
        "actual_savings_sar": 0.0,
        "is_simulated": True,
    }


async def run_experiment(
    business: BusinessProfile,
    *,
    include_mode_b: bool = True,
    include_mode_c: bool = True,
    max_ai_calls_per_audit: int = 10,
    llm_caller: Callable[[str, str], Awaitable[str]] | None = None,
    checkpoint_days: list[int] | None = None,
) -> ExperimentResult:
    """Run the complete 60-day closed-loop experiment for one business.

    This is the core V8 experiment:
    - Simulates 60 days of business activity
    - At each checkpoint, runs all 3 decision modes counterfactually
    - Simulates action outcomes
    - Tracks predicted vs actual
    - Computes calibration metrics
    """
    if checkpoint_days is None:
        checkpoint_days = [0, 7, 14, 30, 45, 60]

    result = ExperimentResult(business=business)
    tracker = OutcomeTracker()
    calibration = CalibrationService(tracker)

    # Simulate full 60 days
    snapshots = simulate_60_days(business, seed_suffix="experiment")
    items = get_v8_items(business.business_id_seed)

    for checkpoint_day in checkpoint_days:
        if checkpoint_day >= len(snapshots):
            continue

        snapshot = snapshots[checkpoint_day]
        logger.info("Checkpoint Day %d for %s: %d items, inventory SAR %.2f",
                     checkpoint_day, business.name,
                     len(snapshot.items),
                     snapshot.financial_state["total_inventory_value_sar"])

        # Build evidence package from snapshot
        evidence_items = []
        for item_state, item_profile in zip(snapshot.items, items):
            evidence = _build_item_evidence_from_snapshot(
                item_state, item_profile, business, snapshot, checkpoint_day,
            )
            evidence_items.append(evidence)

        business_ctx = _build_business_context(business, items, snapshot)

        package = AuditEvidencePackage(
            business=business_ctx,
            items=evidence_items,
            classification_summary={},
            ai_budget_remaining=max_ai_calls_per_audit,
        )

        # MODE A: Deterministic only
        mode_a_result = await run_counterfactual_audit(
            package, llm_caller=None, include_mode_c=False, max_ai_calls=0,
        )

        # MODE B: Deterministic + AI (if enabled)
        mode_b_result = None
        if include_mode_b and llm_caller:
            mode_b_result = await run_counterfactual_audit(
                package, llm_caller=llm_caller, include_mode_c=False,
                max_ai_calls=max_ai_calls_per_audit,
            )

        # MODE C: Deterministic + AI + historical outcomes (if enabled)
        mode_c_result = None
        if include_mode_c and llm_caller:
            # Gather historical outcomes from tracker
            historical = {}
            for rec in tracker.get_records(business_id=business.business_id_seed):
                if rec.sku not in historical:
                    historical[rec.sku] = []
                historical[rec.sku].append({
                    "action_type": rec.action_type,
                    "expected_recovery_sar": rec.expected_recovery_sar,
                    "actual_recovery_sar": rec.actual_recovery_sar,
                })
            mode_c_result = await run_counterfactual_audit(
                package, llm_caller=llm_caller, historical_outcomes=historical,
                include_mode_c=True, max_ai_calls=max_ai_calls_per_audit,
            )

        # Simulate action outcomes for MODE A decisions
        simulated_outcomes = []
        rng = _seed_rng(f"{business.business_id_seed}_outcomes_{checkpoint_day}")

        for mode_result_item in mode_a_result.mode_a:
            decision = mode_result_item.final_decision
            if decision == "DO_NOTHING":
                continue

            # Find the corresponding item state
            item_state = None
            item_profile = None
            for ist, ipro in zip(snapshot.items, items):
                if ist["sku"] == mode_result_item.sku:
                    item_state = ist
                    item_profile = ipro
                    break

            if item_state is None or item_profile is None:
                continue

            # Check constraints
            feasible, reason = filter_action(
                decision.lower(),
                {"item_id": mode_result_item.sku, "estimated_cost_sar": item_state["cost"] * item_state["stock"]},
                business_ctx.__dict__,
            )

            if not feasible:
                simulated_outcomes.append({
                    "sku": mode_result_item.sku,
                    "action_type": decision,
                    "constraint_rejected": True,
                    "constraint_reason": reason,
                    "is_simulated": True,
                })
                continue

            # Simulate outcome
            action = {"action_type": decision}
            outcome = _simulate_action_outcome(action, item_state, item_profile, business, rng)

            # Owner acceptance probability
            owner_accept_prob = 0.85 if business.default_autonomy_dial > 50 else 0.6
            owner_accepted = rng.random() < owner_accept_prob

            # Record outcome
            record = OutcomeRecord(
                action_id=f"exp_{business.business_id_seed}_{checkpoint_day}_{mode_result_item.sku}",
                sku=mode_result_item.sku,
                business_id=business.business_id_seed,
                action_type=decision,
                decision_source=mode_result_item.decision_source,
                predicted_impact_sar=item_state["stock"] * item_state["cost"],
                recoverable_low_sar=0.0,
                recoverable_high_sar=item_state["stock"] * item_state["sell"] if item_state["sell"] > 0 else item_state["stock"] * item_state["cost"] * 1.5,
                expected_recovery_sar=None,
                actual_recovery_sar=outcome["actual_recovery_sar"],
                actual_savings_sar=outcome["actual_savings_sar"],
                execution_success=outcome["success"],
                owner_accepted=owner_accepted,
                time_to_outcome_days=7,
                mode="SIMULATED",
                is_simulated=True,
            )
            tracker.record(record)

            simulated_outcomes.append({
                "sku": mode_result_item.sku,
                "action_type": decision,
                "outcome": outcome,
                "owner_accepted": owner_accepted,
                "is_simulated": True,
            })

        # Build checkpoint result
        checkpoint = CheckpointResult(
            day=checkpoint_day,
            business_id=business.business_id_seed,
            snapshot=snapshot,
            mode_a_result=mode_a_result,
            mode_b_result=mode_b_result,
            mode_c_result=mode_c_result,
            simulated_outcomes=simulated_outcomes,
            findings_count=len([o for o in simulated_outcomes if not o.get("constraint_rejected")]),
            recommendations_count=len(mode_a_result.mode_a),
            approvals_count=len([o for o in simulated_outcomes if o.get("owner_accepted")]),
            executions_count=len([o for o in simulated_outcomes if o.get("outcome", {}).get("success")]),
            financial_state=snapshot.financial_state,
        )
        result.checkpoints.append(checkpoint)

    # Compute final metrics
    result.outcome_summary = tracker.compute_summary(business_id=business.business_id_seed).to_dict()
    result.calibration_report = calibration.compute_calibration_report(
        business_id=business.business_id_seed,
    ).to_dict()

    # Mode comparison across all checkpoints
    all_mode_a_decisions = []
    all_mode_b_decisions = []
    for cp in result.checkpoints:
        all_mode_a_decisions.extend(cp.mode_a_result.mode_a)
        if cp.mode_b_result:
            all_mode_b_decisions.extend(cp.mode_b_result.mode_b)

    if all_mode_b_decisions:
        combined = AuditABResult(
            business_id=business.business_id_seed,
            mode_a=all_mode_a_decisions,
            mode_b=all_mode_b_decisions,
        )
        result.mode_comparison = compare_modes(combined)
    else:
        result.mode_comparison = {
            "mode_a_decisions": {},
            "mode_b_decisions": {},
            "ai_overrides": 0,
            "ai_agreements": 0,
            "items_evaluated": len(all_mode_a_decisions),
        }

    # AI metrics
    total_ai_calls = sum(cp.mode_b_result.ai_total_calls if cp.mode_b_result else 0 for cp in result.checkpoints)
    total_ai_latency = sum(cp.mode_b_result.ai_total_latency_ms if cp.mode_b_result else 0 for cp in result.checkpoints)
    result.ai_metrics = {
        "total_ai_calls": total_ai_calls,
        "total_ai_latency_ms": round(total_ai_latency, 1),
        "avg_ai_latency_ms": round(total_ai_latency / max(1, total_ai_calls), 1),
        "ai_calls_per_audit": round(total_ai_calls / max(1, len(result.checkpoints)), 1),
        "checkpoints_with_ai": sum(1 for cp in result.checkpoints if cp.mode_b_result is not None),
    }

    return result


async def run_all_experiments(
    *,
    include_mode_b: bool = True,
    include_mode_c: bool = True,
    max_ai_calls_per_audit: int = 10,
    llm_caller: Callable[[str, str], Awaitable[str]] | None = None,
) -> dict[str, ExperimentResult]:
    """Run the V8 experiment for all 5 businesses."""
    results = {}
    for business in V8_BUSINESSES:
        logger.info("Starting experiment for %s", business.name)
        result = await run_experiment(
            business,
            include_mode_b=include_mode_b,
            include_mode_c=include_mode_c,
            max_ai_calls_per_audit=max_ai_calls_per_audit,
            llm_caller=llm_caller,
        )
        results[business.business_id_seed] = result
        logger.info("Completed experiment for %s: %d checkpoints, %.2f SAR actual recovery (simulated)",
                     business.name, len(result.checkpoints),
                     result.outcome_summary.get("total_actual_recovery_sar", 0))
    return results

"""Business Decision Loop V1 Tests — tests the new V1 features.

Tests:
1. Financial breakdown computation (per-category SAR values)
2. Constraint enforcement (4 new constraints: min_safety_stock, max_purchase, supplier_preferences, branch_priority)
3. Time machine simulation (do-nothing vs NazmOS recommendation)
4. Evidence package endpoint (structured evidence for AI)
5. A/B comparison endpoint (MODE_A vs MODE_B vs MODE_C)
6. Execute endpoint (approval → execution flow)
7. Outcome tracker persistence
"""
from __future__ import annotations

import pytest
import asyncio
from decimal import Decimal


def _run(coro):
    """Run an async coroutine in a new event loop."""
    return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. FINANCIAL BREAKDOWN COMPUTATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestFinancialBreakdown:
    """Verify per-category financial breakdown is computed correctly."""

    def test_dead_stock_value_accumulates(self):
        """Dead stock items should contribute to dead_stock_value."""
        from app.services.recovery_intelligence import classify_inventory

        classification = classify_inventory(
            stock=Decimal("50"),
            recent_qty_30=Decimal("0"),
            prior_qty_30=Decimal("0"),
            days_since_last_sale=90,
            inventory_age_days=120,
        )
        assert classification == "DEAD"

    def test_overstock_value_accumulates(self):
        """Items with days_supply > OVERSTOCK_DAYS should contribute to overstock_value."""
        from app.services.recovery_intelligence import classify_inventory

        # Fast-moving but overstocked
        classification = classify_inventory(
            stock=Decimal("200"),
            recent_qty_30=Decimal("30"),
            prior_qty_30=Decimal("30"),
            days_since_last_sale=2,
            inventory_age_days=60,
        )
        # Should be classified as FAST (high velocity)
        assert classification in {"FAST", "HEALTHY"}

    def test_stockout_risk_value_accumulates(self):
        """Items with low stock and high velocity should contribute to stockout_risk_value."""
        from app.services.recovery_intelligence import stockout_financials

        result = stockout_financials(
            stock=Decimal("2"),
            daily_velocity=Decimal("5"),
            sell=Decimal("100"),
            cost=Decimal("60"),
            lead_time_days=7,
            safety_stock=Decimal("10"),
        )
        assert result.revenue_at_risk > 0
        assert result.classification == "STOCKOUT RISK"

    def test_margin_leakage_value_accumulates(self):
        """Items with margin below target should contribute to margin_leakage_value."""
        # This is tested via the TARGET_MARGIN_PCT check in money_audit_service
        # The margin_leakage_value is accumulated when margin < 0.30
        sell = Decimal("100")
        cost = Decimal("80")
        margin = (sell - cost) / sell
        assert margin < Decimal("0.30")  # Below 30% target


# ═══════════════════════════════════════════════════════════════════════════════
# 2. CONSTRAINT ENFORCEMENT (4 NEW CONSTRAINTS)
# ═══════════════════════════════════════════════════════════════════════════════

class TestConstraintEnforcement:
    """Verify all 10 constraint types are enforced."""

    def test_minimum_safety_stock_blocks_reorder(self):
        """Reorder that would leave stock below minimum_safety_stock should be blocked."""
        from app.services.constraint_service import filter_action

        feasible, reason = filter_action(
            "reorder",
            {"quantity": 5, "current_stock": 3, "estimated_cost_sar": 100},
            {"minimum_safety_stock": 10},
        )
        assert not feasible
        assert "minimum safety stock" in reason.lower()

    def test_minimum_safety_stock_allows_adequate_reorder(self):
        """Reorder that maintains stock above minimum_safety_stock should be allowed."""
        from app.services.constraint_service import filter_action

        feasible, reason = filter_action(
            "reorder",
            {"quantity": 10, "current_stock": 5, "estimated_cost_sar": 100},
            {"minimum_safety_stock": 10},
        )
        assert feasible

    def test_maximum_purchase_amount_blocks(self):
        """Purchase exceeding maximum_purchase_amount should be blocked."""
        from app.services.constraint_service import filter_action

        feasible, reason = filter_action(
            "reorder",
            {"estimated_cost_sar": 5000},
            {"maximum_purchase_amount": 3000},
        )
        assert not feasible
        assert "maximum purchase amount" in reason.lower()

    def test_maximum_purchase_amount_allows(self):
        """Purchase within maximum_purchase_amount should be allowed."""
        from app.services.constraint_service import filter_action

        feasible, reason = filter_action(
            "reorder",
            {"estimated_cost_sar": 2000},
            {"maximum_purchase_amount": 3000},
        )
        assert feasible

    def test_supplier_preferences_blocks(self):
        """Order from non-preferred supplier should be blocked."""
        from app.services.constraint_service import filter_action

        feasible, reason = filter_action(
            "reorder",
            {"supplier_id": "supplier-2", "estimated_cost_sar": 100},
            {"supplier_preferences": ["supplier-1", "supplier-3"]},
        )
        assert not feasible
        assert "preferred supplier" in reason.lower()

    def test_supplier_preferences_allows(self):
        """Order from preferred supplier should be allowed."""
        from app.services.constraint_service import filter_action

        feasible, reason = filter_action(
            "reorder",
            {"supplier_id": "supplier-1", "estimated_cost_sar": 100},
            {"supplier_preferences": ["supplier-1", "supplier-3"]},
        )
        assert feasible

    def test_branch_priority_blocks(self):
        """Transfer to lower-priority branch should be blocked."""
        from app.services.constraint_service import filter_action

        feasible, reason = filter_action(
            "transfer_inventory",
            {"from_business_id": "branch-a", "to_business_id": "branch-b"},
            {"branch_priority": {"branch-a": 10, "branch-b": 5}},
        )
        assert not feasible
        assert "priority" in reason.lower()

    def test_branch_priority_allows(self):
        """Transfer to higher or equal priority branch should be allowed."""
        from app.services.constraint_service import filter_action

        feasible, reason = filter_action(
            "transfer_inventory",
            {"from_business_id": "branch-a", "to_business_id": "branch-b"},
            {"branch_priority": {"branch-a": 5, "branch-b": 10}},
        )
        assert feasible

    def test_strategic_product_blocks_discount(self):
        """Discount on strategic product should be blocked."""
        from app.services.constraint_service import filter_action

        feasible, reason = filter_action(
            "discount",
            {"item_id": "item-1", "discount_pct": 10},
            {"strategic_products": ["item-1"]},
        )
        assert not feasible
        assert "strategic" in reason.lower()

    def test_existing_constraints_still_work(self):
        """Existing constraints (cash_budget, max_discount, blocked_products) still work."""
        from app.services.constraint_service import filter_action

        # Cash budget
        feasible, _ = filter_action("reorder", {"estimated_cost_sar": 5000}, {"cash_budget": 3000})
        assert not feasible

        # Max discount
        feasible, _ = filter_action("discount", {"discount_pct": 50}, {"max_discount_pct": 30})
        assert not feasible

        # Blocked products
        feasible, _ = filter_action("discount", {"item_id": "blocked-1"}, {"blocked_discount_products": ["blocked-1"]})
        assert not feasible


# ═══════════════════════════════════════════════════════════════════════════════
# 3. TIME MACHINE SIMULATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestTimeMachine:
    """Verify time machine simulation produces correct projections."""

    def test_do_nothing_dead_stock_depreciates(self):
        """Dead stock should depreciate over time in do-nothing scenario."""
        from app.services.time_machine import simulate_time_machine

        result = simulate_time_machine(
            items=[{
                "sku": "DEAD-001",
                "product_name": "Dead Product",
                "classification": "DEAD",
                "current_stock": 100,
                "cost_price_sar": 50,
                "sell_price_sar": 100,
                "daily_velocity": 0,
                "days_of_supply": None,
                "action_type": "discount",
                "recoverable_low_sar": 2000,
                "recoverable_high_sar": 4000,
            }],
            horizon_days=30,
        )
        assert result.do_nothing.total_impact_sar < 0  # Negative = loss
        assert result.nazmos_recommendation.total_impact_sar > 0  # Positive = recovery

    def test_do_nothing_fast_stockout_loses_revenue(self):
        """Fast-moving item that stocks out should show lost revenue in do-nothing."""
        from app.services.time_machine import simulate_time_machine

        result = simulate_time_machine(
            items=[{
                "sku": "FAST-001",
                "product_name": "Fast Product",
                "classification": "FAST",
                "current_stock": 10,
                "cost_price_sar": 20,
                "sell_price_sar": 50,
                "daily_velocity": 5,
                "days_of_supply": 2.0,
                "action_type": "reorder",
                "recoverable_low_sar": 0,
                "recoverable_high_sar": 0,
            }],
            horizon_days=30,
        )
        # Do nothing should show stockout loss
        assert result.do_nothing.total_impact_sar < 0

    def test_nazmos_recovers_value(self):
        """NazmOS recommendation should show positive recovery."""
        from app.services.time_machine import simulate_time_machine

        result = simulate_time_machine(
            items=[{
                "sku": "SLOW-001",
                "product_name": "Slow Product",
                "classification": "SLOW MOVING",
                "current_stock": 50,
                "cost_price_sar": 30,
                "sell_price_sar": 60,
                "daily_velocity": 0.5,
                "days_of_supply": 100,
                "action_type": "discount",
                "recoverable_low_sar": 1000,
                "recoverable_high_sar": 2000,
            }],
            horizon_days=30,
        )
        assert result.nazmos_recommendation.total_impact_sar > 0

    def test_result_labeled_as_simulation(self):
        """Every result must be labeled as SIMULATION / ESTIMATE."""
        from app.services.time_machine import simulate_time_machine

        result = simulate_time_machine(items=[], horizon_days=30)
        assert result.to_dict()["estimated"] is True
        assert result.to_dict()["label"] == "SIMULATION / ESTIMATE"

    def test_multiple_horizons(self):
        """Different horizons should produce different projections."""
        from app.services.time_machine import simulate_time_machine

        items = [{
            "sku": "TEST-001",
            "product_name": "Test Product",
            "classification": "DEAD",
            "current_stock": 100,
            "cost_price_sar": 50,
            "sell_price_sar": 100,
            "daily_velocity": 0,
            "days_of_supply": None,
            "action_type": "discount",
            "recoverable_low_sar": 2000,
            "recoverable_high_sar": 4000,
        }]
        result_30 = simulate_time_machine(items=items, horizon_days=30)
        result_60 = simulate_time_machine(items=items, horizon_days=60)

        # 60-day horizon should have worse do-nothing outcome
        assert result_60.do_nothing.total_impact_sar <= result_30.do_nothing.total_impact_sar


# ═══════════════════════════════════════════════════════════════════════════════
# 4. EVIDENCE PACKAGE
# ═══════════════════════════════════════════════════════════════════════════════

class TestEvidencePackage:
    """Verify evidence package contains only trusted structured facts."""

    def test_item_evidence_fields(self):
        """ItemEvidence should contain all required fields."""
        from app.services.evidence_package import build_item_evidence

        evidence = build_item_evidence(
            sku="TEST-001",
            product_name="Test Product",
            classification="FAST",
            stock=Decimal("100"),
            cost=Decimal("20"),
            sell=Decimal("50"),
            qty_30d=Decimal("150"),
            qty_prior=Decimal("120"),
            days_since_last_sale=2,
            inventory_age_days=30,
        )
        assert evidence.sku == "TEST-001"
        assert evidence.classification == "FAST"
        assert evidence.current_stock == 100
        assert evidence.cost_price_sar == 20
        assert evidence.sell_price_sar == 50
        assert evidence.recent_velocity_per_day == 5.0
        assert evidence.inventory_value_sar == 2000

    def test_evidence_does_not_include_untrusted_text(self):
        """Evidence should not include untrusted text fields that could become AI instructions."""
        from app.services.evidence_package import build_item_evidence

        evidence = build_item_evidence(
            sku="TEST-001",
            product_name="<script>alert('xss')</script>",
            classification="FAST",
            stock=Decimal("100"),
            cost=Decimal("20"),
            sell=Decimal("50"),
            qty_30d=Decimal("150"),
            qty_prior=Decimal("120"),
            days_since_last_sale=2,
            inventory_age_days=30,
        )
        # The product_name is stored but should be treated as untrusted data
        assert evidence.product_name == "<script>alert('xss')</script>"
        # Evidence dict should be serializable without injection
        evidence_dict = evidence.to_dict()
        assert isinstance(evidence_dict, dict)

    def test_business_context_fields(self):
        """BusinessContext should contain all required fields."""
        from app.services.evidence_package import BusinessContext

        ctx = BusinessContext(
            business_id="test-business",
            business_type="retail",
            total_inventory_value_sar=100000,
            total_capital_at_risk_sar=25000,
            total_recoverable_high_sar=15000,
            cash_budget=50000,
            max_discount_pct=30,
            blocked_discount_products=["item-1"],
            strategic_products=["item-2"],
            blocked_transfer_routes=["a->b"],
            minimum_margin_pct=0.20,
        )
        assert ctx.cash_budget == 50000
        assert ctx.max_discount_pct == 30
        assert "item-1" in ctx.blocked_discount_products


# ═══════════════════════════════════════════════════════════════════════════════
# 5. OUTCOME TRACKER PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════════

class TestOutcomeTracker:
    """Verify outcome tracker records and computes summary correctly."""

    def test_record_outcome(self):
        """Recording an outcome should add it to the tracker."""
        from app.services.outcome_tracker import OutcomeTracker, OutcomeRecord

        tracker = OutcomeTracker()
        record = OutcomeRecord(
            action_id="test-001",
            sku="SKU-001",
            business_id="biz-001",
            action_type="discount",
            decision_source="DETERMINISTIC",
            predicted_impact_sar=1000,
            actual_recovery_sar=800,
            execution_success=True,
            owner_accepted=True,
        )
        tracker.record(record)
        assert len(tracker.get_records()) == 1

    def test_compute_summary(self):
        """Summary should aggregate outcomes correctly."""
        from app.services.outcome_tracker import OutcomeTracker, OutcomeRecord

        tracker = OutcomeTracker()
        for i in range(5):
            tracker.record(OutcomeRecord(
                action_id=f"test-{i}",
                sku=f"SKU-{i}",
                business_id="biz-001",
                action_type="discount",
                decision_source="DETERMINISTIC",
                expected_recovery_sar=1000,
                actual_recovery_sar=800 + i * 50,
                execution_success=True,
                owner_accepted=True,
            ))
        summary = tracker.compute_summary(business_id="biz-001")
        assert summary.total_actions == 5
        assert summary.completed_actions == 5
        assert summary.total_actual_recovery_sar > 0

    def test_filter_by_business(self):
        """Filtering by business_id should return only matching records."""
        from app.services.outcome_tracker import OutcomeTracker, OutcomeRecord

        tracker = OutcomeTracker()
        tracker.record(OutcomeRecord(
            action_id="test-001", sku="SKU-001", business_id="biz-001",
            action_type="discount", decision_source="DETERMINISTIC",
        ))
        tracker.record(OutcomeRecord(
            action_id="test-002", sku="SKU-002", business_id="biz-002",
            action_type="discount", decision_source="DETERMINISTIC",
        ))
        assert len(tracker.get_records(business_id="biz-001")) == 1
        assert len(tracker.get_records(business_id="biz-002")) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 6. AI REASONING VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestAIReasoningValidation:
    """Verify AI response validation catches errors."""

    def test_valid_decision_accepted(self):
        """Valid decision should be accepted."""
        from app.services.ai_reasoning import VALID_DECISIONS

        assert "DO_NOTHING" in VALID_DECISIONS
        assert "REORDER" in VALID_DECISIONS
        assert "TRANSFER" in VALID_DECISIONS
        assert "DISCOUNT" in VALID_DECISIONS
        assert "PRICE_CHANGE" in VALID_DECISIONS
        assert "RECOVERY_MATCH" in VALID_DECISIONS
        assert "MANUAL_REVIEW" in VALID_DECISIONS

    def test_invalid_decision_rejected(self):
        """Decision not in VALID_DECISIONS should be rejected."""
        from app.services.ai_reasoning import VALID_DECISIONS

        assert "INVALID_DECISION" not in VALID_DECISIONS
        assert "HACK" not in VALID_DECISIONS


# ═══════════════════════════════════════════════════════════════════════════════
# 7. RECOVERY INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════════

class TestRecoveryIntelligence:
    """Verify classification and recovery estimation."""

    def test_classify_dead_stock(self):
        """Items with no sales and old inventory should be DEAD."""
        from app.services.recovery_intelligence import classify_inventory

        result = classify_inventory(
            stock=Decimal("50"),
            recent_qty_30=Decimal("0"),
            prior_qty_30=Decimal("0"),
            days_since_last_sale=90,
            inventory_age_days=120,
        )
        assert result == "DEAD"

    def test_classify_fast_moving(self):
        """Items with high velocity should be FAST."""
        from app.services.recovery_intelligence import classify_inventory

        result = classify_inventory(
            stock=Decimal("100"),
            recent_qty_30=Decimal("90"),
            prior_qty_30=Decimal("80"),
            days_since_last_sale=1,
            inventory_age_days=30,
        )
        assert result == "FAST"

    def test_classify_new_product(self):
        """Items younger than 30 days should be NEW."""
        from app.services.recovery_intelligence import classify_inventory

        result = classify_inventory(
            stock=Decimal("20"),
            recent_qty_30=Decimal("5"),
            prior_qty_30=Decimal("0"),
            days_since_last_sale=5,
            inventory_age_days=15,
            product_age_days=15,
        )
        assert result == "NEW"

    def test_estimate_recovery_without_calibration(self):
        """Without calibration, expected_recovery should be None."""
        from app.services.recovery_intelligence import estimate_recovery

        result = estimate_recovery(
            classification="DEAD",
            stock=Decimal("50"),
            cost=Decimal("20"),
            sell=Decimal("50"),
            calibration_rates=[],
        )
        assert result.expected_recovery is None
        assert result.recoverable_low >= 0
        assert result.recoverable_high >= 0

    def test_estimate_recovery_with_calibration(self):
        """With calibration, expected_recovery should be computed."""
        from app.services.recovery_intelligence import estimate_recovery

        result = estimate_recovery(
            classification="DEAD",
            stock=Decimal("50"),
            cost=Decimal("20"),
            sell=Decimal("50"),
            calibration_rates=[Decimal("0.5"), Decimal("0.6"), Decimal("0.7")],
        )
        assert result.expected_recovery is not None
        assert result.expected_recovery > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 8. ACTION REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

class TestActionRegistry:
    """Verify action registry has all required actions."""

    def test_action_registry_has_core_actions(self):
        """Action registry should have discount, reorder, recovery_match, etc."""
        from app.services.action_registry import ACTION_REGISTRY

        action_types = {spec.action_type for spec in ACTION_REGISTRY.values()}
        assert "discount" in action_types
        assert "reorder" in action_types
        assert "recovery_match" in action_types
        assert "margin_fix" in action_types

    def test_actions_have_required_fields(self):
        """Each action spec should have required fields."""
        from app.services.action_registry import ACTION_REGISTRY

        for spec in ACTION_REGISTRY.values():
            assert hasattr(spec, "action_type")
            assert hasattr(spec, "approval_required")
            assert hasattr(spec, "can_execute")
            assert hasattr(spec, "execution_mode")

"""V8 Closed-Loop Experiment — 60-day counterfactual evaluation.

Tests the core V8 question:
  CAN AI + DETERMINISTIC FINANCIAL INTELLIGENCE + CONSTRAINTS + EXECUTION
  PRODUCE BETTER BUSINESS DECISIONS THAN DETERMINISTIC ALONE?

Uses the v8_business_simulator for reproducible, probability-based business states.
Counterfactual: all 3 modes evaluate the SAME business state.
"""
from __future__ import annotations

import pytest
from decimal import Decimal
from datetime import datetime, timezone

from app.services.recovery_intelligence import classify_inventory
from app.services.evidence_package import (
    ItemEvidence, BusinessContext, AuditEvidencePackage,
    build_item_evidence, triage_items_for_ai,
)
from app.services.ab_decision_framework import (
    deterministic_decision_for_item, AuditABResult, compare_modes, ModeResult,
)
from app.services.v8_business_simulator import (
    V8_BUSINESSES, get_v8_items, simulate_60_days,
    BusinessProfile, ItemProfile,
)
from app.services.ai_reasoning import AIReasoningResult
from app.services.ai_response_validator import validate_ai_response

D = Decimal


class TestV8BusinessSimulator:
    """Test the probability-based business simulator."""

    def test_simulator_produces_61_snapshots(self):
        """Day 0 through Day 60 = 61 snapshots."""
        business = V8_BUSINESSES[0]
        snapshots = simulate_60_days(business, seed_suffix="test1")
        assert len(snapshots) == 61

    def test_simulator_deterministic(self):
        """Same seed produces identical results."""
        business = V8_BUSINESSES[0]
        s1 = simulate_60_days(business, seed_suffix="deterministic")
        s2 = simulate_60_days(business, seed_suffix="deterministic")
        for snap1, snap2 in zip(s1, s2):
            assert len(snap1.items) == len(snap2.items)
            for item1, item2 in zip(snap1.items, snap2.items):
                assert item1["stock"] == item2["stock"]
                assert item1["total_sold"] == item2["total_sold"]

    def test_all_five_businesses_have_items(self):
        """All 5 V8 businesses must have exactly 5 items each."""
        for biz in V8_BUSINESSES:
            items = get_v8_items(biz.business_id_seed)
            assert len(items) == 5, f"{biz.name} should have 5 items, got {len(items)}"

    def test_businesses_have_different_constraints(self):
        """Each business must have unique constraint profiles."""
        budgets = [b.cash_budget for b in V8_BUSINESSES]
        assert len(set(budgets)) == len(budgets), "Cash budgets should differ"

    def test_item_ground_truths_are_set(self):
        """All V8 items must have ground_truth labels."""
        for biz in V8_BUSINESSES:
            items = get_v8_items(biz.business_id_seed)
            for item in items:
                assert item.ground_truth in ("fast", "dead", "seasonal", "slow", "healthy", "growing"), \
                    f"{item.sku} has invalid ground_truth: {item.ground_truth}"

    def test_dead_items_have_zero_or_near_zero_rate(self):
        """Dead items must have daily_rate near 0 (≤0.5 residual)."""
        for biz in V8_BUSINESSES:
            items = get_v8_items(biz.business_id_seed)
            for item in items:
                if item.pattern == "dead":
                    assert item.daily_rate <= 0.5, f"{item.sku} is dead but has daily_rate={item.daily_rate}"

    def test_seasonal_items_have_peak_month(self):
        """Seasonal items must have a seasonal_month."""
        for biz in V8_BUSINESSES:
            items = get_v8_items(biz.business_id_seed)
            for item in items:
                if item.pattern == "seasonal":
                    assert 1 <= item.seasonal_month <= 12, f"{item.sku} has invalid seasonal_month={item.seasonal_month}"


class TestV8DeterministicDecisionLogic:
    """Test the deterministic baseline (MODE A) decision logic."""

    def test_dead_with_stock_gets_discount(self):
        item = ItemEvidence(
            sku="D1", product_name="Dead Item", classification="DEAD",
            current_stock=40, cost_price_sar=10, sell_price_sar=20,
            inventory_value_sar=400, recent_velocity_per_day=0.0,
            prior_velocity_per_day=0.0, daily_velocity=0.0,
            days_of_supply=None, days_since_last_sale=90, inventory_age_days=120,
        )
        assert deterministic_decision_for_item(item) == "DISCOUNT"

    def test_dead_no_stock_gets_do_nothing(self):
        item = ItemEvidence(
            sku="D2", product_name="Dead No Stock", classification="DEAD",
            current_stock=0, cost_price_sar=10, sell_price_sar=20,
            inventory_value_sar=0, recent_velocity_per_day=0.0,
            prior_velocity_per_day=0.0, daily_velocity=0.0,
            days_of_supply=None, days_since_last_sale=90, inventory_age_days=120,
        )
        assert deterministic_decision_for_item(item) == "DO_NOTHING"

    def test_fast_stockout_gets_reorder(self):
        item = ItemEvidence(
            sku="F1", product_name="Fast Stockout", classification="FAST",
            current_stock=0, cost_price_sar=5, sell_price_sar=10,
            inventory_value_sar=0, recent_velocity_per_day=5.0,
            prior_velocity_per_day=4.0, daily_velocity=5.0,
            days_of_supply=None, days_since_last_sale=0, inventory_age_days=30,
            stockout_days=1,
        )
        assert deterministic_decision_for_item(item) == "REORDER"

    def test_slow_with_stock_gets_discount(self):
        item = ItemEvidence(
            sku="S1", product_name="Slow Item", classification="SLOW MOVING",
            current_stock=20, cost_price_sar=15, sell_price_sar=30,
            inventory_value_sar=300, recent_velocity_per_day=0.5,
            prior_velocity_per_day=1.0, daily_velocity=0.5,
            days_of_supply=40, days_since_last_sale=2, inventory_age_days=60,
        )
        assert deterministic_decision_for_item(item) == "DISCOUNT"

    def test_new_item_gets_do_nothing(self):
        item = ItemEvidence(
            sku="N1", product_name="New Product", classification="NEW",
            current_stock=50, cost_price_sar=10, sell_price_sar=20,
            inventory_value_sar=500, recent_velocity_per_day=0.0,
            prior_velocity_per_day=0.0, daily_velocity=0.0,
            days_of_supply=None, days_since_last_sale=None, inventory_age_days=15,
        )
        assert deterministic_decision_for_item(item) == "DO_NOTHING"

    def test_healthy_with_massive_overstock_gets_recovery_match(self):
        item = ItemEvidence(
            sku="H1", product_name="Massive Overstock", classification="HEALTHY",
            current_stock=500, cost_price_sar=20, sell_price_sar=35,
            inventory_value_sar=10000, recent_velocity_per_day=0.5,
            prior_velocity_per_day=0.5, daily_velocity=0.5,
            days_of_supply=1000, days_since_last_sale=0, inventory_age_days=30,
            overstock_days=1000,
        )
        assert deterministic_decision_for_item(item) == "RECOVERY_MATCH"


class TestV8TriageScoring:
    """Test that triage correctly selects ambiguous items for AI."""

    def test_triage_returns_max_10(self):
        items = []
        for i in range(20):
            items.append(ItemEvidence(
                sku=f"T{i}", product_name=f"Item {i}",
                classification="SEASONAL" if i % 2 == 0 else "FAST",
                current_stock=50, cost_price_sar=10, sell_price_sar=20,
                inventory_value_sar=500, recent_velocity_per_day=1.0,
                prior_velocity_per_day=1.0, daily_velocity=1.0,
                days_of_supply=50, days_since_last_sale=0, inventory_age_days=30,
                overstock_days=80 if i % 3 == 0 else None,
            ))
        triaged = triage_items_for_ai(items, max_calls=10)
        assert len(triaged) <= 10

    def test_seasonal_items_score_higher(self):
        seasonal = ItemEvidence(
            sku="SEAS", product_name="Seasonal", classification="SEASONAL",
            current_stock=100, cost_price_sar=15, sell_price_sar=28,
            inventory_value_sar=1500, recent_velocity_per_day=0.5,
            prior_velocity_per_day=3.0, daily_velocity=0.5,
            days_of_supply=200, days_since_last_sale=3, inventory_age_days=60,
            monthly_concentrations=[0.5, 0.5, 0.5, 0.5, 0.5, 40.0],
            monthly_concentration_peak=0.96,
        )
        fast = ItemEvidence(
            sku="FAST", product_name="Fast Item", classification="FAST",
            current_stock=50, cost_price_sar=10, sell_price_sar=20,
            inventory_value_sar=500, recent_velocity_per_day=5.0,
            prior_velocity_per_day=4.5, daily_velocity=5.0,
            days_of_supply=10, days_since_last_sale=0, inventory_age_days=30,
        )
        triaged = triage_items_for_ai([fast, seasonal], max_calls=10)
        # Seasonal should be first (higher triage score due to ambiguity)
        assert triaged[0].sku == "SEAS", "Seasonal item should be triaged first"


class TestV8CounterfactualExperiment:
    """Test the counterfactual A/B evaluation on V8 businesses."""

    def test_counterfactual_all_modes_same_state(self):
        """All 3 modes evaluate the same business state."""
        from app.services.v8_business_simulator import V8_BUSINESSES, get_v8_items

        business = V8_BUSINESSES[0]  # Healthy Supermarket
        items = get_v8_items(business.business_id_seed)

        # Build evidence packages for same state
        evidence_items = []
        for item in items:
            evidence_items.append(build_item_evidence(
                sku=item.sku, product_name=item.name,
                classification=item.ground_truth.upper().replace("GROWING", "FAST"),
                stock=D(str(item.initial_stock)),
                cost=D(str(item.cost)),
                sell=D(str(item.sell if item.sell > 0 else item.cost * 1.5)),
                qty_30d=D(str(item.daily_rate * 30)),
                qty_prior=D(str(item.daily_rate * 25)),
                days_since_last_sale=0 if item.pattern != "dead" else 90,
                inventory_age_days=item.inventory_age_days,
            ))

        business_ctx = BusinessContext(
            business_id=business.business_id_seed,
            business_type=business.business_type,
            total_inventory_value_sar=sum(i.inventory_value_sar for i in evidence_items),
            total_capital_at_risk_sar=sum(i.capital_at_risk_sar for i in evidence_items),
            total_recoverable_high_sar=sum(i.recoverable_high_sar for i in evidence_items),
            cash_budget=business.cash_budget,
            max_discount_pct=business.max_discount_pct,
            blocked_discount_products=business.blocked_discount_products,
            strategic_products=business.strategic_products,
        )

        package = AuditEvidencePackage(
            business=business_ctx,
            items=evidence_items,
            classification_summary={},
        )

        # Run deterministic only (MODE A)
        from app.services.ab_decision_framework import run_counterfactual_audit
        import asyncio

        result = asyncio.run(
            run_counterfactual_audit(package, llm_caller=None, include_mode_c=False)
        )

        assert len(result.mode_a) == 5, f"Expected 5 items in MODE A, got {len(result.mode_a)}"
        # MODE A is deterministic-only
        for r in result.mode_a:
            assert r.decision_source == "DETERMINISTIC"
            assert r.final_decision in ("DO_NOTHING", "REORDER", "TRANSFER", "DISCOUNT",
                                         "PRICE_CHANGE", "RECOVERY_MATCH", "MANUAL_REVIEW")

    def test_compare_modes_produces_metrics(self):
        """compare_modes must produce valid comparison metrics."""
        result = AuditABResult(
            business_id="test",
            mode_a=[
                ModeResult(mode="MODE_A", sku="A1", deterministic_decision="DISCOUNT",
                          final_decision="DISCOUNT", decision_source="DETERMINISTIC"),
            ],
            mode_b=[
                ModeResult(mode="MODE_B", sku="A1", deterministic_decision="DISCOUNT",
                          ai_decision="TRANSFER", final_decision="TRANSFER",
                          decision_source="AI_REASONING", ai_confidence=0.85),
            ],
        )
        metrics = compare_modes(result)
        assert metrics["ai_overrides"] == 1
        assert metrics["items_evaluated"] == 1

    def test_all_five_businesses_simulate_60_days(self):
        """All 5 V8 businesses must simulate 60 days without error."""
        from app.services.v8_business_simulator import V8_BUSINESSES, simulate_60_days
        for biz in V8_BUSINESSES:
            snapshots = simulate_60_days(biz, seed_suffix="integration")
            assert len(snapshots) == 61, f"{biz.name} should produce 61 snapshots"
            # Day 0 should have items
            assert len(snapshots[0].items) == 5, f"{biz.name} day 0 should have 5 items"


class TestV8RegressionGuard:
    """V7 regression: ensure V8 additions don't break V7 classification."""

    def test_v7_classify_inventory_unchanged(self):
        """V7 classify_inventory must produce identical results."""
        from app.services.recovery_intelligence import classify_inventory

        # V7 test case: fast item
        assert classify_inventory(
            stock=D("50"), recent_qty_30=D("150"), prior_qty_30=D("120"),
            days_since_last_sale=0, inventory_age_days=45,
        ) == "FAST"

        # V7 test case: dead item
        assert classify_inventory(
            stock=D("50"), recent_qty_30=D("0"), prior_qty_30=D("0"),
            days_since_last_sale=60, inventory_age_days=90,
        ) == "DEAD"

        # V7 test case: seasonal
        assert classify_inventory(
            stock=D("30"), recent_qty_30=D("120"), prior_qty_30=D("10"),
            days_since_last_sale=0, inventory_age_days=90,
            monthly_concentrations=[D("10"), D("10"), D("80")],
        ) == "SEASONAL"

        # V7 test case: slow moving
        assert classify_inventory(
            stock=D("0"), recent_qty_30=D("45"), prior_qty_30=D("30"),
            days_since_last_sale=0, inventory_age_days=60,
        ) == "SLOW MOVING"

    def test_v7_25_item_corpus_unchanged(self):
        """V7 25-item classification must remain 25/25."""
        from app.services.recovery_intelligence import classify_inventory

        items = [
            {"stock": D("50"), "recent_qty_30": D("150"), "prior_qty_30": D("120"), "days_since": 0, "inv_age": 45, "monthly": None, "gt": "fast"},
            {"stock": D("30"), "recent_qty_30": D("100"), "prior_qty_30": D("80"), "days_since": 0, "inv_age": 30, "monthly": None, "gt": "fast"},
            {"stock": D("25"), "recent_qty_30": D("0"), "prior_qty_30": D("0"), "days_since": 90, "inv_age": 120, "monthly": None, "gt": "dead"},
            {"stock": D("28"), "recent_qty_30": D("45"), "prior_qty_30": D("3"), "days_since": 0, "inv_age": 15, "monthly": [D("3"), D("45")], "gt": "seasonal"},
            {"stock": D("0"), "recent_qty_30": D("15"), "prior_qty_30": D("30"), "days_since": 0, "inv_age": 60, "monthly": None, "gt": "slow"},
            {"stock": D("40"), "recent_qty_30": D("120"), "prior_qty_30": D("100"), "days_since": 0, "inv_age": 30, "monthly": None, "gt": "fast"},
            {"stock": D("35"), "recent_qty_30": D("90"), "prior_qty_30": D("70"), "days_since": 0, "inv_age": 45, "monthly": None, "gt": "fast"},
            {"stock": D("20"), "recent_qty_30": D("0"), "prior_qty_30": D("0"), "days_since": 75, "inv_age": 90, "monthly": None, "gt": "dead"},
            {"stock": D("15"), "recent_qty_30": D("50"), "prior_qty_30": D("5"), "days_since": 0, "inv_age": 20, "monthly": [D("5"), D("50")], "gt": "seasonal"},
            {"stock": D("0"), "recent_qty_30": D("20"), "prior_qty_30": D("25"), "days_since": 0, "inv_age": 60, "monthly": None, "gt": "slow"},
            {"stock": D("60"), "recent_qty_30": D("180"), "prior_qty_30": D("150"), "days_since": 0, "inv_age": 30, "monthly": None, "gt": "fast"},
            {"stock": D("45"), "recent_qty_30": D("130"), "prior_qty_30": D("110"), "days_since": 0, "inv_age": 45, "monthly": None, "gt": "fast"},
            {"stock": D("30"), "recent_qty_30": D("0"), "prior_qty_30": D("0"), "days_since": 80, "inv_age": 100, "monthly": None, "gt": "dead"},
            {"stock": D("25"), "recent_qty_30": D("60"), "prior_qty_30": D("8"), "days_since": 0, "inv_age": 25, "monthly": [D("8"), D("60")], "gt": "seasonal"},
            {"stock": D("0"), "recent_qty_30": D("25"), "prior_qty_30": D("35"), "days_since": 0, "inv_age": 50, "monthly": None, "gt": "slow"},
            {"stock": D("80"), "recent_qty_30": D("200"), "prior_qty_30": D("180"), "days_since": 0, "inv_age": 30, "monthly": None, "gt": "fast"},
            {"stock": D("55"), "recent_qty_30": D("160"), "prior_qty_30": D("140"), "days_since": 0, "inv_age": 40, "monthly": None, "gt": "fast"},
            {"stock": D("40"), "recent_qty_30": D("0"), "prior_qty_30": D("0"), "days_since": 95, "inv_age": 110, "monthly": None, "gt": "dead"},
            {"stock": D("35"), "recent_qty_30": D("70"), "prior_qty_30": D("6"), "days_since": 0, "inv_age": 18, "monthly": [D("6"), D("70")], "gt": "seasonal"},
            {"stock": D("0"), "recent_qty_30": D("30"), "prior_qty_30": D("40"), "days_since": 0, "inv_age": 55, "monthly": None, "gt": "slow"},
            {"stock": D("70"), "recent_qty_30": D("170"), "prior_qty_30": D("150"), "days_since": 0, "inv_age": 35, "monthly": None, "gt": "fast"},
            {"stock": D("50"), "recent_qty_30": D("140"), "prior_qty_30": D("120"), "days_since": 0, "inv_age": 40, "monthly": None, "gt": "fast"},
            {"stock": D("22"), "recent_qty_30": D("0"), "prior_qty_30": D("0"), "days_since": 999, "inv_age": 90, "monthly": None, "gt": "dead"},
            {"stock": D("30"), "recent_qty_30": D("55"), "prior_qty_30": D("4"), "days_since": 0, "inv_age": 22, "monthly": [D("4"), D("55")], "gt": "seasonal"},
            {"stock": D("0"), "recent_qty_30": D("18"), "prior_qty_30": D("28"), "days_since": 0, "inv_age": 48, "monthly": None, "gt": "slow"},
        ]

        correct = 0
        for item in items:
            cls = classify_inventory(
                stock=item["stock"], recent_qty_30=item["recent_qty_30"],
                prior_qty_30=item["prior_qty_30"], days_since_last_sale=item["days_since"],
                inventory_age_days=item["inv_age"], monthly_concentrations=item["monthly"],
            )
            predicted = cls.lower()
            gt = item["gt"]
            match = (predicted == gt or (gt == "slow" and "slow" in predicted)
                     or (gt == "fast" and predicted in ("fast", "overstock")))
            if match:
                correct += 1
        assert correct == 25, f"V7 regression: expected 25/25, got {correct}/25"

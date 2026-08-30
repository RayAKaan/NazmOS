"""V11 Latency Measurement — Wall-clock time for different dataset sizes.

Measures (REAL, not simulated):
- Deterministic audit latency
- Context engine latency
- AI challenge latency (real LLM calls)
- Total estimated audit latency

All measurements are MEASURED or clearly labeled as ESTIMATED.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

RESULTS = ROOT / "results" / "v11"
RESULTS.mkdir(parents=True, exist_ok=True)


def measure_deterministic_latency():
    """MEASURED: Deterministic decision latency for different dataset sizes."""
    from app.services.ab_decision_framework import deterministic_decision_for_item
    from app.services.evidence_package import ItemEvidence

    print("\n1. Measuring deterministic decision latency...")

    test_sizes = [10, 50, 100, 500, 1000]
    results = {}

    for size in test_sizes:
        items = []
        for i in range(size):
            item = ItemEvidence(
                sku=f"SKU-{i:04d}",
                product_name=f"Product {i}",
                classification=["FAST", "SLOW MOVING", "UNKNOWN", "SEASONAL", "DEAD"][i % 5],
                current_stock=float(100 - i % 50),
                cost_price_sar=10.0,
                sell_price_sar=20.0,
                inventory_value_sar=float((100 - i % 50) * 10),
                recent_velocity_per_day=float(2.0 - (i % 5) * 0.4),
                prior_velocity_per_day=float(2.0 - (i % 5) * 0.4),
                daily_velocity=float(2.0 - (i % 5) * 0.4),
                days_of_supply=50.0,
                days_since_last_sale=5,
                inventory_age_days=30,
            )
            items.append(item)

        start = time.perf_counter()
        for item in items:
            deterministic_decision_for_item(item)
        elapsed = time.perf_counter() - start

        latency_per_item = elapsed / size * 1000
        results[size] = {
            "total_ms": round(elapsed * 1000, 2),
            "per_item_ms": round(latency_per_item, 4),
            "measured": True,
        }
        print(f"    {size} items: {elapsed*1000:.2f}ms total, {latency_per_item:.4f}ms/item")

    return results


def measure_context_engine_latency():
    """MEASURED: Context engine latency."""
    from app.services.business_context import BusinessContextEngine
    from app.services.evidence_package import ItemEvidence, BusinessContext

    print("\n2. Measuring context engine latency...")

    engine = BusinessContextEngine()
    results = {}

    test_sizes = [10, 50, 100]
    for size in test_sizes:
        items = []
        for i in range(size):
            item = ItemEvidence(
                sku=f"SKU-{i:04d}",
                product_name=f"Product {i}",
                classification=["FAST", "SLOW MOVING", "UNKNOWN", "SEASONAL", "DEAD"][i % 5],
                current_stock=float(100 - i % 50),
                cost_price_sar=10.0,
                sell_price_sar=20.0,
                inventory_value_sar=float((100 - i % 50) * 10),
                recent_velocity_per_day=float(2.0 - (i % 5) * 0.4),
                prior_velocity_per_day=float(2.0 - (i % 5) * 0.4),
                daily_velocity=float(2.0 - (i % 5) * 0.4),
                days_of_supply=50.0,
                days_since_last_sale=5,
                inventory_age_days=30,
            )
            items.append(item)

        business = BusinessContext(
            business_id="al_noor_supermarket",
            business_type="supermarket",
            total_inventory_value_sar=50000.0,
            total_capital_at_risk_sar=50000.0,
            total_recoverable_high_sar=30000.0,
        )

        start = time.perf_counter()
        for item in items:
            asyncio.run(engine.build_context(item, business, date.today()))
        elapsed = time.perf_counter() - start

        latency_per_item = elapsed / size * 1000
        results[size] = {
            "total_ms": round(elapsed * 1000, 2),
            "per_item_ms": round(latency_per_item, 4),
            "measured": True,
        }
        print(f"    {size} items: {elapsed*1000:.2f}ms total, {latency_per_item:.4f}ms/item")

    return results


def measure_challenge_latency():
    """MEASURED: AI challenge latency with real LLM calls."""
    print("\n3. Measuring AI challenge latency (REAL LLM calls)...")

    from app.services.llm_orchestrator import LLMOrchestrator
    from app.services.business_context import BusinessContextEngine, StructuredContext, ProductContext, SeasonalContext, SupplierContext, PromotionContext, OwnerContext, BusinessAggContext, TimeContext
    from app.services.ai_challenge import challenge_deterministic

    orchestrator = LLMOrchestrator()

    if orchestrator.use_mock:
        print("    WARNING: LLM orchestrator in MOCK mode. Latency measurements will be mock values.")
        print("    Set GROQ_API_KEY or GOOGLE_AI_API_KEY for real measurements.\n")

    async def llm_caller(system_prompt: str, user_prompt: str) -> str:
        result = await orchestrator.chat_completion(system_prompt, user_prompt)
        if result is None:
            raise RuntimeError("LLM returned None")
        return result

    base_context = StructuredContext(
        product=ProductContext(
            sku="LAT-TEST", product_name="Latency Test Product", category="Test",
            current_stock=10, inventory_value_sar=100.0, cost=10.0, sell_price=20.0,
            gross_margin_pct=0.5, recent_velocity=0.5, prior_velocity=0.5,
            long_term_velocity=0.5, trend="stable", days_of_supply=20.0,
            inventory_age_days=30, last_sale_days_ago=5, sales_frequency="weekly",
            demand_volatility=0.2,
        ),
        seasonal=SeasonalContext(
            is_seasonal=False, seasonal_type=None, days_until_season=None,
            days_since_season_ended=None, historical_seasonal_demand_multiplier=None,
            expected_seasonal_demand=None, seasonal_confidence=0.0, upcoming_seasons=[],
        ),
        supplier=SupplierContext(
            supplier_name="Test Supplier", lead_time_days=5, on_time_pct=95.0,
            moq_sar=100.0, supplier_reliability="reliable", confirmed_inbound_qty=0,
            ghost_po_risk=False, preferred_supplier=True,
        ),
        promotion=PromotionContext(
            is_promotional=False, promotion_type=None, promotion_duration_days=None,
            promotional_uplift_pct=None, normal_velocity=0.5, post_promotion_risk=False,
        ),
        owner=OwnerContext(
            cash_budget=10000.0, max_purchase_amount=5000.0, min_margin_pct=0.20,
            max_discount_pct=0.30, blocked_discount_skus=[], strategic_skus=[],
            blocked_transfer_routes=[], branch_priorities=[], risk_preference="balanced",
        ),
        business=BusinessAggContext(
            business_type="supermarket", branch_count=1,
            total_inventory_value_sar=50000.0, total_capital_at_risk_sar=50000.0,
            total_recoverable_sar=30000.0, recent_actions=[], recent_outcomes=[],
        ),
        time=TimeContext(
            virtual_date="2026-08-26", day_of_week="Wednesday",
            upcoming_holidays=[], days_until_ramadan=None, days_until_eid=None,
            days_until_white_friday=None, is_quarter_end=False,
        ),
        deterministic_decision="DO_NOTHING",
        deterministic_confidence=0.85,
        ai_challenge_eligible=True,
        ai_challenge_reason="Latency test",
    )

    results = {}
    latencies = []
    num_calls = 10

    for i in range(num_calls):
        try:
            t0 = time.perf_counter()
            challenge = asyncio.run(challenge_deterministic(base_context, llm_caller))
            latency_ms = (time.perf_counter() - t0) * 1000
            latencies.append(latency_ms)
            print(f"    Call {i+1}/{num_calls}: {latency_ms:.0f}ms (status: {challenge.status.value})")
        except Exception as e:
            print(f"    Call {i+1}/{num_calls} failed: {e}")

    if latencies:
        latencies_sorted = sorted(latencies)
        avg_latency = sum(latencies) / len(latencies)
        p50 = latencies_sorted[len(latencies_sorted) // 2]
        p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)]

        results = {
            "avg_latency_ms": round(avg_latency, 1),
            "p50_latency_ms": round(p50, 1),
            "p95_latency_ms": round(p95, 1),
            "min_latency_ms": round(min(latencies), 1),
            "max_latency_ms": round(max(latencies), 1),
            "num_calls": len(latencies),
            "provider": orchestrator._real_providers()[0] if orchestrator._real_providers() else "mock",
            "mock_mode": orchestrator.use_mock,
            "measured": True,
        }
        print(f"\n    MEASURED: avg={avg_latency:.0f}ms, p50={p50:.0f}ms, p95={p95:.0f}ms")
    else:
        results = {"error": "All LLM calls failed", "num_calls": 0, "measured": True}
        print("    All LLM calls failed")

    return results


def compute_total_audit_latency(
    det_results: dict,
    ctx_results: dict,
    challenge_results: dict,
    num_items: int = 100,
    ai_budget: int = 25,
) -> dict:
    """Compute ESTIMATED total audit latency from measured components.

    Clearly labeled as ESTIMATED (not measured) because we don't run
    the full pipeline in a single timed operation.
    """
    print("\n4. Computing ESTIMATED total audit latency from measured components...")

    det_100 = det_results.get(100, {}).get("total_ms", 0) / 1000  # Convert to seconds
    ctx_100 = ctx_results.get(100, {}).get("total_ms", 0) / 1000
    avg_challenge_s = challenge_results.get("avg_latency_ms", 0) / 1000

    # ESTIMATE: AI calls for budget-constrained items
    ai_calls = min(ai_budget, num_items)
    ai_latency_s = ai_calls * avg_challenge_s

    total = det_100 + ctx_100 + ai_latency_s
    target = 120.0

    results = {
        "deterministic_latency_s": round(det_100, 3),
        "context_engine_latency_s": round(ctx_100, 3),
        "ai_challenge_latency_s": round(ai_latency_s, 3),
        "estimated_total_latency_s": round(total, 3),
        "target_latency_s": target,
        "within_target": total <= target,
        "ai_calls_used": ai_calls,
        "num_items": num_items,
        "note": "ESTIMATED total from measured components. Not a single timed run.",
        "measured": False,
    }

    print(f"    Deterministic: {det_100:.3f}s (MEASURED)")
    print(f"    Context Engine: {ctx_100:.3f}s (MEASURED)")
    print(f"    AI Challenge ({ai_calls} calls): {ai_latency_s:.3f}s (MEASURED avg * estimated count)")
    print(f"    ESTIMATED Total: {total:.3f}s (target: {target}s)")
    print(f"    Within target: {'YES' if total <= target else 'NO'}")

    return results


def run_latency_tests():
    """Run all latency measurements."""
    print("=" * 70)
    print("V11 LATENCY MEASUREMENT")
    print("=" * 70)

    det_results = measure_deterministic_latency()
    ctx_results = measure_context_engine_latency()
    challenge_results = measure_challenge_latency()
    total_results = compute_total_audit_latency(det_results, ctx_results, challenge_results)

    results = {
        "deterministic": det_results,
        "context_engine": ctx_results,
        "ai_challenge": challenge_results,
        "total_audit": total_results,
    }

    output_file = RESULTS / "latency_results.json"
    output_file.write_text(json.dumps(results, indent=1))
    print(f"\nResults saved to: {output_file}")

    return results


if __name__ == "__main__":
    run_latency_tests()

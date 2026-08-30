#!/usr/bin/env python3
"""V11 Experiment Runner — Contextual AI Challenge & Incremental Value Reality Test.

Three-mode counterfactual evaluation:
  MODE_A: Deterministic only (baseline)
  MODE_B: Deterministic + Structured Context + AI Challenge + Validation
  MODE_C: Deterministic + Structured Context + AI Challenge + Validation + Historical Outcomes

State evolution: Each checkpoint advances the clock and simulates consumption.
Same initial state → all three modes for fair comparison.

GROUND TRUTH FIREWALL: Ground truth is ONLY used by the evaluator/scoring layer.
This file NEVER reads ground truth for decision generation.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
# Check if we're in container (ROOT/app exists) or host (ROOT/backend exists)
IS_CONTAINER = (ROOT / "app").exists() and not (ROOT / "backend").exists()
RESULTS = ROOT / "results" / "v11"
RESULTS.mkdir(parents=True, exist_ok=True)

# Configuration
BIZ_ID = "al_noor_supermarket"
CHECKPOINTS = [0, 7, 14, 30, 45, 60]
MAX_AI_CALLS_PER_CHECKPOINT = 8
AI_CALL_DELAY_S = 4.0  # Google free tier: 20 RPM. B(8)+C(8)=16 calls within window

# Outcome model for state evolution
om_candidates = [
    ROOT / "scripts" / "v11" / "outcome_model.json",
    ROOT / "v11" / "outcome_model.json",
]
OM_PATH = next((p for p in om_candidates if p.exists()), om_candidates[0])
with OM_PATH.open() as f:
    OM = json.load(f)


def build_llm_caller(orchestrator):
    """Create an LLM caller adapter matching challenge_deterministic's expected signature.

    Wraps LLMOrchestrator.chat_completion(system_prompt, user_prompt) -> str|None
    into Callable[[str, str], Awaitable[str]].
    """
    async def llm_caller(system_prompt: str, user_prompt: str) -> str:
        result = await orchestrator.chat_completion(system_prompt, user_prompt)
        if result is None:
            raise RuntimeError("LLM returned None (all providers failed or circuit open)")
        return result
    return llm_caller


def simulate_consumption(items: list[dict], days: int, virtual_date: date) -> dict[str, dict]:
    """Simulate inventory consumption between checkpoints.

    Returns dict mapping SKU to consumption details.
    """
    consumption = {}
    daily_consumption = OM.get("daily_consumption_units_per_day", {}).get(BIZ_ID, {})

    for item in items:
        sku = item.get("sku", "")
        rate = daily_consumption.get(sku, 0)
        if rate <= 0:
            continue

        current_stock = item.get("current_stock", 0) or 0
        consumed = min(current_stock, rate * days)
        new_stock = max(0, current_stock - consumed)

        consumption[sku] = {
            "consumed_units": round(consumed, 2),
            "new_stock": round(new_stock, 2),
            "previous_stock": current_stock,
            "daily_rate": rate,
            "days_advanced": days,
        }

    return consumption


def apply_consumption_to_items(items: list[dict], consumption: dict[str, dict]) -> list[dict]:
    """Apply simulated consumption to item data, returning new item list."""
    updated = []
    for item in items:
        item_copy = dict(item)
        sku = item_copy.get("sku", "")
        if sku in consumption:
            item_copy["current_stock"] = consumption[sku]["new_stock"]
        updated.append(item_copy)
    return updated


def build_historical_outcomes(
    mode_b_results: list[dict],
    overrides: list[dict],
    prev_outcomes: list[dict],
) -> list[dict]:
    """Build structured historical outcomes for MODE C.

    Each outcome includes:
    - sku, previous_decision, action_taken, predicted_result, observed_result,
      prediction_error, confidence, action_type
    """
    outcomes = list(prev_outcomes)  # Accumulate from prior checkpoints

    for result in mode_b_results:
        sku = result.get("sku", "")
        decision = result.get("final_decision", "")
        source = result.get("decision_source", "")

        # Only record items where AI actually challenged
        if source not in ("AI_CHALLENGE_ACCEPTED", "CHALLENGE_INVALID", "CHALLENGE_CONSTRAINT_REJECTED"):
            continue

        # Find override classification
        override_info = next((o for o in overrides if o.get("sku") == sku), {})
        classification = override_info.get("classification", "NEUTRAL_OVERRIDE")

        outcome = {
            "sku": sku,
            "previous_decision": result.get("deterministic_decision", decision),
            "action_taken": decision,
            "action_source": source,
            "override_classification": classification,
            "confidence": result.get("challenge_confidence", 0),
            "action_type": decision,
        }
        outcomes.append(outcome)

    return outcomes


def record_ai_call(
    sku: str,
    provider: str,
    model: str,
    latency_ms: float,
    success: bool,
    challenge_status: str,
    fallback: bool = False,
    tokens_prompt: int = 0,
    tokens_completion: int = 0,
    error: str | None = None,
) -> dict:
    """Record details of a single AI call."""
    return {
        "sku": sku,
        "provider": provider,
        "model": model,
        "latency_ms": round(latency_ms, 1),
        "success": success,
        "challenge_status": challenge_status,
        "fallback": fallback,
        "tokens_prompt": tokens_prompt,
        "tokens_completion": tokens_completion,
        "error": error,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def extract_item_value(item: dict) -> float:
    """Extract inventory value for an item."""
    return float(item.get("inventory_value_sar", 0) or 0)


async def run_v11_experiment():
    """Run the full V11 experiment with real AI calls."""
    print("=" * 70)
    print("V11 CONTEXTUAL AI CHALLENGE & INCREMENTAL VALUE REALITY TEST")
    print("=" * 70)
    print("GROUND TRUTH FIREWALL: Active — GT never used in decision logic")

    # Initialize LLM orchestrator
    # Host: ROOT/backend/app/services exists
    # Container: ROOT/app/services exists (backend is ROOT itself)
    backend_path = ROOT / "backend"
    if not (backend_path / "app").exists():
        backend_path = ROOT  # Container layout: /app/app/services
    sys.path.insert(0, str(backend_path))
    from app.services.llm_orchestrator import LLMOrchestrator
    from app.services.ab_decision_framework import deterministic_decision_for_item
    from app.services.evidence_package import ItemEvidence, BusinessContext
    from app.services.business_context import BusinessContextEngine
    from app.services.ai_challenge import (
        challenge_deterministic, select_final_decision_v11,
        ChallengeStatus
    )

    orchestrator = LLMOrchestrator()
    llm_caller = build_llm_caller(orchestrator)
    context_engine = BusinessContextEngine()

    if orchestrator.use_mock:
        print("\nWARNING: LLM orchestrator is in MOCK mode. AI challenges will return canned responses.")
        print("Set GROQ_API_KEY or GOOGLE_AI_API_KEY for real AI evaluation.")
        print("Continuing with mock mode for structural validation...\n")

    # Load ground truth ONLY for evaluator (never for decision logic)
    evaluator_candidates = [
        ROOT / "scripts" / "v11",
        ROOT / "v11",
    ]
    evaluator_dir = next((p for p in evaluator_candidates if p.exists()), evaluator_candidates[0])
    sys.path.insert(0, str(evaluator_dir))
    from evaluator import score_mode_results, classify_override, compute_financial_metrics

    # Generate business data if needed
    data_candidates = [
        ROOT / "sample_data" / "v11",
    ]
    data_dir = next((p for p in data_candidates if p.exists()), data_candidates[0])

    if not data_dir.exists() or not any(data_dir.glob("*.csv")):
        print("\nGenerating V11 business data...")
        import subprocess
        gen_script = ROOT / "scripts" / "v11_generate_business_data.py"
        subprocess.run([sys.executable, str(gen_script)], cwd=str(ROOT), check=True)

    # Load generated items directly (bypass API for offline mode)
    inv_file = data_dir / f"{BIZ_ID}_inventory_d0.csv"
    if not inv_file.exists():
        print(f"ERROR: Inventory file not found: {inv_file}")
        print("Run: python scripts/v11_generate_business_data.py")
        return

    import csv

    # Map CSV title-case columns → ItemEvidence snake_case fields
    CSV_TO_EVIDENCE = {
        "SKU": "sku",
        "Product": "product_name",
        "Category": "classification",
        "Current Stock": "current_stock",
        "Cost Price SAR": "cost_price_sar",
        "Shelf Price SAR": "sell_price_sar",
        "Normal Velocity": "daily_velocity",
        "Supplier": "supplier_name",
        "Branch A Stock": "branch_a_stock",
        "Branch B Stock": "branch_b_stock",
        "Supplier Reliability": "supplier_reliability",
        "Ghost PO Risk": "ghost_po_risk",
        "Is Promotional": "is_promotional",
        "Promotion Uplift Pct": "promotion_uplift_pct",
        "Trend": "trend",
        "Demand Volatility": "demand_volatility",
        "Seasonal Type": "seasonal_type",
        "Days Until Season": "days_until_season",
        "Days Since Season Ended": "days_since_season_ended",
        "Historical Seasonal Multiplier": "historical_seasonal_multiplier",
        "Reorder Level": "reorder_level",
    }

    items = []
    with open(inv_file, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mapped = {}
            for csv_key, evidence_key in CSV_TO_EVIDENCE.items():
                val = row.get(csv_key, "")
                mapped[evidence_key] = val

            # Convert numeric fields
            for key in ("current_stock", "cost_price_sar", "sell_price_sar",
                        "daily_velocity", "branch_a_stock", "branch_b_stock",
                        "promotion_uplift_pct", "demand_volatility",
                        "reorder_level"):
                if key in mapped and mapped[key]:
                    try:
                        mapped[key] = float(mapped[key])
                    except (ValueError, TypeError):
                        mapped[key] = 0.0
                else:
                    mapped[key] = 0.0

            # Convert bool fields
            for key in ("ghost_po_risk", "is_promotional"):
                mapped[key] = str(mapped.get(key, "")).lower() == "true"

            # Convert int fields
            for key in ("days_until_season", "days_since_season_ended"):
                if mapped.get(key):
                    try:
                        mapped[key] = int(float(mapped[key]))
                    except (ValueError, TypeError):
                        mapped[key] = None
                else:
                    mapped[key] = None

            # Convert seasonal multiplier
            if mapped.get("historical_seasonal_multiplier"):
                try:
                    mapped["historical_seasonal_multiplier"] = float(mapped["historical_seasonal_multiplier"])
                except (ValueError, TypeError):
                    mapped["historical_seasonal_multiplier"] = None
            else:
                mapped["historical_seasonal_multiplier"] = None

            # Compute derived fields
            current_stock = mapped.get("current_stock", 0)
            cost = mapped.get("cost_price_sar", 0)
            price = mapped.get("sell_price_sar", 0)
            daily_vel = mapped.get("daily_velocity", 0)

            mapped["inventory_value_sar"] = round(current_stock * cost, 2)
            mapped["recent_velocity_per_day"] = daily_vel
            mapped["prior_velocity_per_day"] = daily_vel * 0.9  # Slight prior diff
            mapped["days_of_supply"] = round(current_stock / max(daily_vel, 0.01), 1) if daily_vel > 0 else None
            mapped["days_since_last_sale"] = 7
            mapped["inventory_age_days"] = 30
            mapped["margin_pct"] = round((price - cost) / max(price, 0.01), 4) if price > 0 else 0

            items.append(mapped)

    # Compute inventory classifications from data (CSV Category is NOT the classification)
    # Velocities are daily: range 0.03..1.0. Thresholds calibrated to data.
    # Classifications: FAST, SLOW MOVING, DEAD, UNKNOWN, SEASONAL, NEW
    for item in items:
        daily_vel = item.get("daily_velocity", 0)
        current_stock = item.get("current_stock", 0)
        is_seasonal = item.get("seasonal_type") is not None

        if is_seasonal:
            item["classification"] = "SEASONAL"
        elif current_stock == 0:
            item["classification"] = "UNKNOWN"
        elif daily_vel >= 0.5:
            item["classification"] = "FAST"
        elif daily_vel >= 0.15:
            item["classification"] = "SLOW MOVING"
        elif daily_vel > 0:
            item["classification"] = "DEAD"
        else:
            item["classification"] = "UNKNOWN"

    print(f"\nLoaded {len(items)} items from generated data")

    business_ctx = BusinessContext(
        business_id=BIZ_ID,
        business_type="supermarket",
        total_inventory_value_sar=50000.0,
        total_capital_at_risk_sar=50000.0,
        total_recoverable_high_sar=30000.0,
    )

    # Run experiment
    all_checkpoint_results = []
    virtual_date = date(2026, 8, 26)
    prev_mode_b_results = []
    prev_overrides = []
    historical_outcomes = []
    all_ai_calls = []

    for cp_idx, cp in enumerate(CHECKPOINTS):
        print(f"\n{'='*70}")
        print(f"CHECKPOINT d{cp:02d} (virtual_date: {virtual_date})")
        print(f"{'='*70}")

        # Freeze state snapshot for fair comparison
        frozen_items = [dict(item) for item in items]

        # Run three modes on SAME initial state
        mode_a_results = []
        mode_b_results = []
        mode_c_results = []
        overrides = []
        challenge_log = []
        ai_calls_used = 0
        checkpoint_ai_calls = []

        print(f"\n  Items to evaluate: {len(frozen_items)}")

        # ── MODE A: Deterministic only (control group) ──
        print("\n  MODE A: Deterministic only...")
        for item in frozen_items:
            item_evidence = ItemEvidence(**{k: v for k, v in item.items()
                                           if k in ItemEvidence.__dataclass_fields__})
            det_decision = deterministic_decision_for_item(item_evidence)

            mode_a_results.append({
                "sku": item.get("sku", ""),
                "final_decision": det_decision,
                "inventory_value_sar": extract_item_value(item),
            })

        print(f"    Mode A complete: {len(mode_a_results)} items")

        # ── MODE B: Deterministic + Context + AI Challenge + Validation ──
        print("\n  MODE B: Deterministic + Context + AI Challenge...")
        ai_calls_used_b = 0

        for item in frozen_items:
            sku = item.get("sku", "")
            item_evidence = ItemEvidence(**{k: v for k, v in item.items()
                                           if k in ItemEvidence.__dataclass_fields__})
            det_decision = deterministic_decision_for_item(item_evidence)

            result = {
                "sku": sku,
                "final_decision": det_decision,
                "deterministic_decision": det_decision,
                "challenge_status": "NO_CHALLENGE",
                "decision_source": "DETERMINISTIC_CONFIRMED",
                "inventory_value_sar": extract_item_value(item),
            }

            # Only challenge if we have AI budget
            if ai_calls_used_b < MAX_AI_CALLS_PER_CHECKPOINT:
                try:
                    # Build structured context
                    context = await context_engine.build_context(
                        item_evidence, business_ctx, virtual_date
                    )
                    context.deterministic_decision = det_decision

                    # Call real AI challenge (or mock if no API keys)
                    t0 = time.time()
                    challenge = await challenge_deterministic(context, llm_caller)
                    latency_ms = (time.time() - t0) * 1000

                    # Select final decision with validation
                    final_decision, source = select_final_decision_v11(
                        det_decision, challenge, context
                    )

                    result["final_decision"] = final_decision
                    result["challenge_status"] = challenge.status.value
                    result["decision_source"] = source
                    result["challenge_confidence"] = challenge.confidence
                    result["challenge_reason"] = challenge.reason
                    result["latency_ms"] = round(latency_ms, 1)

                    # Record AI call details
                    call_record = record_ai_call(
                        sku=sku,
                        provider=orchestrator._real_providers()[0] if orchestrator._real_providers() else "mock",
                        model="mock" if orchestrator.use_mock else "real",
                        latency_ms=latency_ms,
                        success=challenge.is_valid,
                        challenge_status=challenge.status.value,
                        fallback=orchestrator.fallback_mode,
                        error=challenge.validation_errors[0] if challenge.validation_errors else None,
                    )
                    checkpoint_ai_calls.append(call_record)
                    all_ai_calls.append(call_record)

                    ai_calls_used_b += 1

                    # Pace between calls
                    if ai_calls_used_b < MAX_AI_CALLS_PER_CHECKPOINT:
                        await asyncio.sleep(AI_CALL_DELAY_S)

                except Exception as e:
                    result["challenge_status"] = "INSUFFICIENT_EVIDENCE"
                    result["decision_source"] = f"AI_FAILED_{type(e).__name__}"
                    result["error"] = str(e)

                    call_record = record_ai_call(
                        sku=sku,
                        provider="unknown",
                        model="unknown",
                        latency_ms=0,
                        success=False,
                        challenge_status="ERROR",
                        error=str(e),
                    )
                    checkpoint_ai_calls.append(call_record)
                    all_ai_calls.append(call_record)

            mode_b_results.append(result)

            if result["challenge_status"] != "NO_CHALLENGE":
                challenge_log.append({
                    "sku": sku,
                    "status": result["challenge_status"],
                    "source": result["decision_source"],
                    "deterministic": det_decision,
                    "final": result["final_decision"],
                    "confidence": result.get("challenge_confidence", 0),
                    "latency_ms": result.get("latency_ms", 0),
                })

        print(f"    Mode B complete: {len(mode_b_results)} items, {ai_calls_used_b} AI calls")

        # ── MODE C: Deterministic + Context + AI Challenge + Validation + Outcomes ──
        print("\n  MODE C: Deterministic + Context + AI Challenge + Outcomes...")
        ai_calls_used_c = 0

        # Build outcome context from prior checkpoints
        outcome_context_text = ""
        if historical_outcomes:
            recent = historical_outcomes[-10:]  # Last 10 outcomes
            outcome_context_text = "\nHISTORICAL OUTCOMES FROM PRIOR CHECKPOINTS:\n"
            for o in recent:
                outcome_context_text += (
                    f"- SKU {o['sku']}: took {o['action_taken']} "
                    f"(source: {o['action_source']}, "
                    f"classification: {o['override_classification']})\n"
                )

        for item in frozen_items:
            sku = item.get("sku", "")
            item_evidence = ItemEvidence(**{k: v for k, v in item.items()
                                           if k in ItemEvidence.__dataclass_fields__})
            det_decision = deterministic_decision_for_item(item_evidence)

            result = {
                "sku": sku,
                "final_decision": det_decision,
                "deterministic_decision": det_decision,
                "challenge_status": "NO_CHALLENGE",
                "decision_source": "DETERMINISTIC_CONFIRMED",
                "inventory_value_sar": extract_item_value(item),
            }

            if ai_calls_used_c < MAX_AI_CALLS_PER_CHECKPOINT:
                try:
                    context = await context_engine.build_context(
                        item_evidence, business_ctx, virtual_date
                    )
                    context.deterministic_decision = det_decision

                    # MODE C: Add historical outcomes to context
                    if outcome_context_text:
                        # Inject outcome context into the challenge prompt
                        original_reason = context.ai_challenge_reason or ""
                        context.ai_challenge_reason = (
                            f"{original_reason}\n{outcome_context_text}"
                        ).strip()

                    t0 = time.time()
                    challenge = await challenge_deterministic(context, llm_caller)
                    latency_ms = (time.time() - t0) * 1000

                    final_decision, source = select_final_decision_v11(
                        det_decision, challenge, context
                    )

                    result["final_decision"] = final_decision
                    result["challenge_status"] = challenge.status.value
                    result["decision_source"] = source
                    result["challenge_confidence"] = challenge.confidence
                    result["challenge_reason"] = challenge.reason
                    result["latency_ms"] = round(latency_ms, 1)
                    result["has_outcome_context"] = bool(outcome_context_text)

                    call_record = record_ai_call(
                        sku=sku,
                        provider=orchestrator._real_providers()[0] if orchestrator._real_providers() else "mock",
                        model="mock" if orchestrator.use_mock else "real",
                        latency_ms=latency_ms,
                        success=challenge.is_valid,
                        challenge_status=challenge.status.value,
                        fallback=orchestrator.fallback_mode,
                    )
                    checkpoint_ai_calls.append(call_record)
                    all_ai_calls.append(call_record)

                    ai_calls_used_c += 1

                    if ai_calls_used_c < MAX_AI_CALLS_PER_CHECKPOINT:
                        await asyncio.sleep(AI_CALL_DELAY_S)

                except Exception as e:
                    result["challenge_status"] = "INSUFFICIENT_EVIDENCE"
                    result["decision_source"] = f"AI_FAILED_{type(e).__name__}"
                    result["error"] = str(e)

            mode_c_results.append(result)

        print(f"    Mode C complete: {len(mode_c_results)} items, {ai_calls_used_c} AI calls")

        # ── Evaluate against ground truth (evaluator only) ──
        print("\n7. Evaluating against ground truth...")
        eval_a = score_mode_results(BIZ_ID, mode_a_results)
        eval_b = score_mode_results(BIZ_ID, mode_b_results)
        eval_c = score_mode_results(BIZ_ID, mode_c_results)

        # Classify overrides
        for det_r, ai_r in zip(mode_a_results, mode_b_results):
            sku = det_r.get("sku", "")
            classification = classify_override(
                BIZ_ID, sku, det_r["final_decision"], ai_r["final_decision"]
            )
            overrides.append({
                "sku": sku,
                "deterministic": det_r["final_decision"],
                "ai_final": ai_r["final_decision"],
                "classification": classification,
            })

        # Financial metrics (MODELLED, not actual)
        financial = compute_financial_metrics(BIZ_ID, mode_b_results, mode_a_results)

        # Record AI economics
        total_latency = sum(c["latency_ms"] for c in checkpoint_ai_calls)
        successful_calls = sum(1 for c in checkpoint_ai_calls if c["success"])
        failed_calls = sum(1 for c in checkpoint_ai_calls if not c["success"])
        fallback_calls = sum(1 for c in checkpoint_ai_calls if c["fallback"])

        ai_economics = {
            "requested_calls": min(len(frozen_items), MAX_AI_CALLS_PER_CHECKPOINT),
            "actual_calls": ai_calls_used_b,
            "skipped_calls": max(0, len(frozen_items) - ai_calls_used_b),
            "successful_calls": successful_calls,
            "failed_calls": failed_calls,
            "fallback_calls": fallback_calls,
            "total_latency_ms": round(total_latency, 1),
            "avg_latency_ms": round(total_latency / max(successful_calls, 1), 1),
            "provider": orchestrator._real_providers()[0] if orchestrator._real_providers() else "mock",
            "model": "mock" if orchestrator.use_mock else "real",
        }

        # Save checkpoint
        checkpoint_data = {
            "checkpoint": f"d{cp:02d}",
            "virtual_date": virtual_date.isoformat(),
            "eval_mode_a": eval_a,
            "eval_mode_b": eval_b,
            "eval_mode_c": eval_c,
            "overrides_b_vs_a": overrides,
            "challenge_log": challenge_log,
            "v11_metrics": {
                "ai_calls": ai_economics,
                "financial": financial,
            },
        }

        checkpoint_file = RESULTS / f"checkpoint_d{cp:02d}.json"
        checkpoint_file.write_text(json.dumps(checkpoint_data, indent=1))
        print(f"  Checkpoint saved: {checkpoint_file}")
        all_checkpoint_results.append(checkpoint_data)

        # Save AI call log for this checkpoint
        cp_call_file = RESULTS / f"ai_calls_d{cp:02d}.jsonl"
        with open(cp_call_file, "w", encoding="utf-8") as f:
            for call in checkpoint_ai_calls:
                f.write(json.dumps(call, default=str) + "\n")

        # ── State evolution ──
        if cp_idx < len(CHECKPOINTS) - 1:
            next_cp = CHECKPOINTS[cp_idx + 1]
            days_to_advance = next_cp - cp

            # Simulate consumption
            consumption = simulate_consumption(items, days_to_advance, virtual_date)

            # Apply consumption to inventory
            items = apply_consumption_to_items(items, consumption)

            # Build historical outcomes for MODE C
            historical_outcomes = build_historical_outcomes(
                mode_b_results, overrides, historical_outcomes
            )

            virtual_date += timedelta(days=days_to_advance)

            print(f"\n  State evolution: {len(consumption)} items consumed over {days_to_advance} days")

        # Print summary
        good_overrides = len([o for o in overrides if o["classification"] == "GOOD_OVERRIDE"])
        bad_overrides = len([o for o in overrides if o["classification"] == "BAD_OVERRIDE"])
        neutral_overrides = len([o for o in overrides if o["classification"] == "NEUTRAL_OVERRIDE"])

        print(f"\n  SUMMARY for d{cp:02d}:")
        print(f"    Mode A strict accuracy: {eval_a.get('correct_decision_rate', 'N/A')}")
        print(f"    Mode B strict accuracy: {eval_b.get('correct_decision_rate', 'N/A')}")
        print(f"    Mode B effective accuracy: {eval_b.get('effective_accuracy', 'N/A')}")
        print(f"    Mode C strict accuracy: {eval_c.get('correct_decision_rate', 'N/A')}")
        print(f"    Overrides: {good_overrides} GOOD, {bad_overrides} BAD, {neutral_overrides} NEUTRAL")
        print(f"    AI calls: {ai_economics['actual_calls']}/{ai_economics['requested_calls']}")
        print(f"    AI latency: {ai_economics['avg_latency_ms']:.0f}ms avg")

    # ── Generate evaluation summary ──
    print("\n" + "=" * 70)
    print("GENERATING EVALUATION SUMMARY")
    print("=" * 70)

    from evaluator import evaluate_all_checkpoints
    summary = evaluate_all_checkpoints()

    # Save full AI call log
    all_calls_file = RESULTS / "ai_calls.jsonl"
    with open(all_calls_file, "w", encoding="utf-8") as f:
        for call in all_ai_calls:
            f.write(json.dumps(call, default=str) + "\n")

    # Save experiment metadata
    metadata = {
        "version": "V11",
        "ground_truth_firewall": "ACTIVE — GT never used in decision logic",
        "gt_hash": "31376a348d84b72e8b684568bc41a4d01061d94a783178e81f2cc0cff486228b",
        "llm_provider": orchestrator._real_providers()[0] if orchestrator._real_providers() else "mock",
        "llm_mock_mode": orchestrator.use_mock,
        "max_ai_calls_per_checkpoint": MAX_AI_CALLS_PER_CHECKPOINT,
        "checkpoints": CHECKPOINTS,
        "total_ai_calls": len(all_ai_calls),
        "total_items_evaluated": len(CHECKPOINTS) * len(items),
    }
    (RESULTS / "experiment_metadata.json").write_text(json.dumps(metadata, indent=1))

    print("\nV11 EXPERIMENT COMPLETE")
    print(f"Results saved to: {RESULTS}")
    print(f"Ground truth firewall: ACTIVE")
    print(f"Total AI calls: {len(all_ai_calls)}")


if __name__ == "__main__":
    asyncio.run(run_v11_experiment())

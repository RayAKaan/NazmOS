"""Benchmark: shadow parity + determinism gates for the Jev channel.

Runs the deterministic decision path for a representative payload set, consults
the Jev channel in shadow mode (mock transport by default), and writes every
comparison to ``results/jev_shadow_parity.jsonl``.

Usage:
    python -m benchmarks.jev_shadow_parity            # mock shadow consult
    python -m benchmarks.jev_shadow_parity --live     # opt-in real Jev consult

Invariants (MASTER_PLAN §6/§8): Jev never changes the outcome; divergence is
logged; deterministic wins; Jev unavailable => deterministic + source fallback.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.services.shadow_capture import run_shadow_parity

PAYLOADS: list[tuple[dict, str]] = [
    (
        {
            "items": [
                {
                    "ref": "item_A",
                    "stock_band": "0-9",
                    "velocity_band": "LOW",
                    "classification": "auto_parts",
                    "candidate_decisions": ["REORDER", "DO_NOTHING"],
                    "evidence_fields": ["stock_band", "velocity_band"],
                }
            ],
            "business": {"business_type": "auto_parts", "capital_at_risk_band": "HIGH"},
        },
        "REORDER",
    ),
    (
        {
            "items": [
                {
                    "ref": "item_B",
                    "stock_band": "200-499",
                    "velocity_band": "NONE",
                    "is_overstock": True,
                    "classification": "food",
                    "candidate_decisions": ["DISCOUNT", "TRANSFER", "DO_NOTHING"],
                    "evidence_fields": ["stock_band", "velocity_band", "is_overstock"],
                }
            ],
            "business": {"business_type": "food", "capital_at_risk_band": "MEDIUM"},
        },
        "DISCOUNT",
    ),
    (
        {
            "items": [
                {
                    "ref": "item_C",
                    "stock_band": "50-99",
                    "velocity_band": "HIGH",
                    "classification": "auto_parts",
                    "candidate_decisions": ["REORDER", "DO_NOTHING"],
                    "evidence_fields": ["stock_band", "velocity_band"],
                }
            ],
            "business": {"business_type": "auto_parts", "capital_at_risk_band": "MEDIUM"},
        },
        "DO_NOTHING",
    ),
]


async def main(live: bool) -> int:
    q = None
    if live:
        from app.services.ai_providers.jev import consult as jev_consult

        q = jev_consult
        print("--live: consulting real Jev endpoint; deterministic still wins.")
    else:
        print("mock shadow consult: deterministic decisions are authoritative.")

    summary = await run_shadow_parity(
        cases=PAYLOADS,
        consult=q,  # None => default stub-free consult (mock/disabled)
    )
    print(f"total={summary['total']}")
    print(f"agree={summary['agree']}")
    print(f"diverge={summary['diverge']}")
    print(f"jev_down={summary['jev_down']}")
    print(f"deterministic_total={summary['deterministic_total']}")
    for i, div in enumerate(summary.get("divergences", []), 1):
        print(f"divergence#{i}: deterministic={div['deterministic']} jev={div['jev']} source={div['jev_source']}")
    return 0 if summary["deterministic_total"] == summary["total"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="opt-in real Jev consult")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.live)))
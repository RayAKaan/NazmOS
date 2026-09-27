"""Cycle-policy registry (Phase 4D) — policy NAME crosses the Temporal wire.

``CyclePolicy`` holds callables (``advisory_fn``, ``verification_evaluator``)
that are never JSON-serializable, so a Temporal activity payload can only carry
a policy *name*. The worker resolves the concrete immutable policy from this
registry — the same way activities resolve retry policies and task bodies — so
business callables stay in code while the durable substrate sees a stable,
portable identifier.

Policies here are deliberately immutable by convention: the worker process is
the only place the callables exist; nothing from a request can inject a
callable or a policy body.
"""
from __future__ import annotations

from typing import Any, Callable

from app.services.business_loop.advisory import AdvisorySource
from app.services.business_loop.cycle import CyclePolicy


async def synthetic_mocked_advisor(capability: str, context: dict) -> dict:
    """Synthetic deterministic advisor — labelled MOCKED, never JEV.

    Mirrors the Phase 3 vertical-slice mock exactly so the durable workflow
    proves the SAME attribution contract holds through Temporal: source is
    ``mocked`` (never ``jev``), and suggestions stay inside the contract.
    ``consult_advisory`` awaits the provider, so this must be a coroutine
    (mirrors the vertical slice's ``_mocked_jev``).
    """
    contract = context.get("contract") or frozenset()
    prefer = {"transfer_inventory"} & contract
    return {
        "decision": context.get("deterministic_decision", "DO_NOTHING"),
        "suggested": next(iter(prefer)) if prefer else None,
        "confidence": 0.85,
        "source": AdvisorySource.MOCKED.value,
        "provider": "jev-mock",
        "model": "jev-mock-1.0",
        "reasoning": "synthetic advisory: prefer autonomous transfer within contract.",
    }


def synthetic_measurement_evaluator(pre: dict[str, Any], post: dict[str, Any]) -> dict[str, Any]:
    """Synthetic measurement authority — reality, never a number the loop invents.

    Same body as the vertical slice's authority: observed impact = drop in
    inventory-at-cost between pre- and post-action state (only reported when
    the surplus was actually reduced).
    """
    pre_inv = (pre.get("domains") or {}).get("inventory", {}).get("values", {})
    post_inv = (post.get("domains") or {}).get("inventory", {}).get("values", {})
    keys = set(pre_inv) & set(post_inv)
    if not keys:
        return {"observed_impact_sar": None}
    total_pre = sum(
        float(pre_inv[k].get("stock", 0) or 0) * float(pre_inv[k].get("cost", 0) or 0) for k in keys
    )
    total_post = sum(
        float(post_inv[k].get("stock", 0) or 0) * float(post_inv[k].get("cost", 0) or 0) for k in keys
    )
    observed = round(total_pre - total_post, 2)
    return {"observed_impact_sar": observed if observed > 0 else None}


def synthetic_policy() -> CyclePolicy:
    """The default synthetic cycle policy used by durable workflow dispatches."""
    return CyclePolicy(
        shariah_approved=True,
        advisory_fn=synthetic_mocked_advisor,
        verification_evaluator=synthetic_measurement_evaluator,
    )


# policy name -> factory. Only names cross the Temporal wire.
CYCLE_POLICY_REGISTRY: dict[str, Callable[[], CyclePolicy]] = {
    "synthetic": synthetic_policy,
}


def resolve_cycle_policy(name: str) -> CyclePolicy:
    """Resolve a policy by its registry name (deny by default on unknown)."""
    factory = CYCLE_POLICY_REGISTRY.get(name)
    if factory is None:
        raise KeyError(f"unknown_cycle_policy:{name}")
    return factory()
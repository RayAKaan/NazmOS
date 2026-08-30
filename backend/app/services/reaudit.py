"""Automatic re-audit after actions (Phase 3, §3).

NazmOS must not mark a finding resolved merely because an API call succeeded — the
underlying business state must be re-checked. After an action executes, the relevant
domain is re-audited so the finding can be verified against real data.

action_type → domain(s) mapping keeps this selective (never a full multi-domain audit
after every trivial action).
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("reaudit")

ACTION_DOMAIN_MAP: dict[str, list[str]] = {
    "restock": ["inventory"],
    "transfer_inventory": ["inventory", "recovery_match"],
    "pricing_increase": ["money_audit"],
    "pricing_decrease": ["money_audit"],
    "discount": ["money_audit", "inventory"],
    "margin_fix": ["money_audit"],
    "recovery_match": ["recovery_match"],
}


def domains_for_action(action_type: str) -> list[str]:
    return ACTION_DOMAIN_MAP.get(action_type, [])


async def reaudit_after_execution(
    db: AsyncSession,
    business_id: UUID | str,
    action_type: str,
    commit: bool = True,
) -> dict[str, Any]:
    """Re-run the domain(s) affected by an executed action. Best-effort — a failed
    re-audit must never break the execution that triggered it."""
    from app.services.audit_engine import run_audit

    domains = domains_for_action(action_type)
    results = []
    for domain in domains:
        try:
            results.append(await run_audit(db, business_id, domain, trigger="agent", commit=False))
        except Exception as exc:
            logger.warning("re-audit %s skipped: %s", domain, exc)
            results.append({"domain": domain, "status": "failed", "error": str(exc)[:500]})
    if commit:
        await db.commit()
    return {"action_type": action_type, "reaudited_domains": domains, "audits": results}

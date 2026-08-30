"""Finding approval via WhatsApp (Phase 2, brief §9).

Builds a WHAT / WHY / EVIDENCE / IMPACT / RISK / ACTION message from a Finding and
sends it through the existing WhatsApp bridge. Approval tokens are the action/finding
IDs (UUIDs) — replay-resistant because approve/reject is idempotent per status and
tenant-checked by the agent/finding services. Sensitive data is NOT included in the
message: only the finding title, impact, and risk band.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.whatsapp_bridge import send_approval_request


def _finding_approval_urls(finding_id: UUID | str, app_url: str) -> tuple[str, str]:
    approve_url = f"{app_url}/findings/{finding_id}?action=approve"
    reject_url = f"{app_url}/findings/{finding_id}?action=reject"
    return approve_url, reject_url


def build_finding_message(finding: dict[str, Any]) -> tuple[str, str]:
    """Return (title, summary) for the WhatsApp approval. No sensitive data."""
    impact = finding.get("estimated_financial_impact_sar")
    impact_str = f"SAM {impact:,.0f}" if impact is not None else "n/a"
    title = f"🔎 {finding.get('title', 'Finding')}"
    summary = (
        f"What: {finding.get('explanation') or finding.get('category', '')}\n"
        f"Impact: {impact_str}\n"
        f"Risk: {finding.get('action_risk', 'low')}\n"
        f"Recommended: {(finding.get('recommended_action') or {}).get('type', 'review')}"
    )
    return title, summary


async def request_finding_approval(
    db: AsyncSession,
    business_id: UUID | str,
    finding_id: UUID | str,
    owner_whatsapp: str | None,
    app_url: str = "https://app.nazm.ai",
) -> dict[str, Any]:
    """Send a finding approval request over WhatsApp (mock-safe, falls back to deep link)."""
    if not owner_whatsapp:
        return {"status": "skipped", "reason": "no owner WhatsApp number"}

    res = await db.execute(text("""
        SELECT f.id, f.title, f.explanation, f.category, f.estimated_financial_impact_sar,
               f.recommended_action, f.action_risk
        FROM findings f WHERE f.id = :id AND f.business_id = :b
    """), {"id": str(finding_id), "b": str(business_id)})
    row = res.fetchone()
    if not row:
        return {"status": "skipped", "reason": "finding not found or not owned by business"}

    finding = {
        "title": row.title,
        "explanation": row.explanation,
        "category": row.category,
        "estimated_financial_impact_sar": float(row.estimated_financial_impact_sar) if row.estimated_financial_impact_sar is not None else None,
        "recommended_action": row.recommended_action if isinstance(row.recommended_action, dict) else {},
        "action_risk": row.action_risk,
    }
    title, summary = build_finding_message(finding)
    approve_url, reject_url = _finding_approval_urls(finding_id, app_url)
    result = await send_approval_request(
        owner_whatsapp,
        str(finding_id),
        title,
        summary,
        approve_url,
        reject_url,
        action_prefix="finding_approve",
    )
    return result

"""Recovery Agent (Phase 7, §2–3) — now Finding-driven.

Money Audit remains the domain-specific analytical engine; the audit engine's
`money_audit` domain adapter turns its results into canonical Findings. This agent
now consumes those Findings as the canonical problem representation — never
`list_money_audit_actions` directly — so every proposal carries a `finding_id` that
flows through the runtime into `AgentAction.finding_id` and the graph's RECOMMENDS edge.

Loop:
  1. read actionable money-audit Findings (open, recovery-type);
  2. rank by estimated financial impact × severity;
  3. explain why they matter;
  4. propose recovery actions, each with `finding_id`;
  5. the runtime's policy gate decides approval (low→auto, medium→draft, high→approval);
  6. approved actions execute via the existing deterministic executor;
  7. verify_outcome measures actual recovered value;
  8. actual/revised impact is recorded on the finding + impact ledger.

No autonomous purchasing: restock actions still only create a purchase order under
the autonomy dial (default: draft/pending-approval).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.intelligence.agents.base import BaseAgent


class RecoveryAgent(BaseAgent):
    agent_type = "recovery"
    name = "Recovery Agent"
    objective = "Find money trapped in the store and recover it through approved actions."

    tools = ["generate_money_audit", "find_recovery_matches", "get_inventory", "get_sales", "forecast_demand"]
    read_only = False  # may propose mutating actions, but execution is gated by the runtime
    max_tool_calls = 12
    triggers = ["sale.completed", "inventory.changed", "supplier.delivered"]

    async def propose(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        from app.services.outcome_learning import learning_adjusted_action
        from app.services.constraint_service import get_constraints, filter_action
        from app.services.action_registry import get_action_spec, can_execute
        constraints = await get_constraints(self.session, str(self.business_id))

        # §2: consume canonical Findings (money_audit domain), not raw MoneyAudit actions.
        findings = await self.session.execute(text("""
            SELECT id, title, explanation, category, severity, evidence,
                   estimated_financial_impact_sar, confidence, recommended_action
            FROM findings
            WHERE business_id = :b
              AND domain = 'money_audit'
              AND category != 'money_at_risk'
              AND status NOT IN ('rejected', 'verified', 'failed')
            ORDER BY
              CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
              COALESCE(estimated_financial_impact_sar, 0) DESC
            LIMIT :lim
        """), {"b": str(self.business_id), "lim": self.max_tool_calls})
        rows = findings.fetchall()

        proposals: list[dict[str, Any]] = []
        for r in rows:
            import json
            rec = r.recommended_action if isinstance(r.recommended_action, dict) else (json.loads(r.recommended_action) if r.recommended_action else {})
            evidence = r.evidence if isinstance(r.evidence, dict) else (json.loads(r.evidence) if r.evidence else {})
            original_type = rec.get("type") or "review"

            adjusted = await learning_adjusted_action(self.session, self.business_id, original_type)
            action_type = adjusted["action_type"]
            payload = dict(rec.get("payload") or {})
            if evidence.get("item_id") and "item_id" not in payload:
                payload["item_id"] = evidence.get("item_id")
            feasible, constraint_reason = filter_action(action_type, payload, constraints)
            if not feasible:
                continue

            reason = rec.get("why") or r.explanation or "Recovery opportunity identified by the Money Audit."
            if adjusted.get("adjusted"):
                reason = f"{adjusted['reason']} (was: {reason})"

            proposals.append({
                "action_type": action_type,
                "finding_id": str(r.id),
                "title": r.title,
                "reason": reason,
                "item_id": evidence.get("item_id") or rec.get("item_id"),
                "payload": payload,
                "execution_mode": "AUTONOMOUS" if can_execute(action_type, payload) else "MANUAL",
                "financial_impact_sar": float(r.estimated_financial_impact_sar or 0),
                "expected_recovery_sar": None,
                "recoverable_value_low_sar": None,
                "recoverable_value_high_sar": None,
                "confidence": float(r.confidence or 0.85) if not adjusted.get("adjusted") else 0.6,
                "financial_impact_type": (evidence.get("financial_impact_type") or "UNKNOWN"),
                "recovery_estimation_required": True,
                "evidence": evidence,
                "urgency": 0.9 if r.severity in ("critical", "high") else 0.5,
                "learning_adjusted": adjusted.get("adjusted", False),
            })

        return {
            "agent_type": self.agent_type,
            "proposal_event_type": "agent.proposal",
            "payload": {"proposals": proposals},
            "confidence": 0.85 if proposals else 0.9,
            "reasons": ["Ranked recovery findings from the canonical money-audit domain"],
        }

    async def verify_outcome(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Phase 8 §4: measure impact per-finding where possible; only fall back to a
        business-level metric when per-finding attribution is impossible, and mark the
        attribution scope explicitly. Never present a business delta as per-action impact."""
        from app.services.impact_ledger_service import record_impact, finding_observed_impact
        from app.services.money_audit_service import get_latest_money_audit

        # Per-finding attribution when the runtime passed a finding_id via context.
        finding_id = (context or {}).get("finding_id")
        if finding_id:
            observed = await finding_observed_impact(self.session, self.business_id, finding_id)
            # Direct/partial entries already exist → nothing more to write; report them.
            direct = observed["direct_sar"]
            if observed["entries"] > 0 and direct >= 0:
                return {
                    "verified": observed["total_verified_sar"] > 0,
                    "attribution_scope": "finding",
                    "finding_id": str(finding_id),
                    "direct_impact_sar": direct,
                    "partial_impact_sar": observed["partial_sar"],
                    "note": f"Per-finding impact: SAR {direct:,.0f} direct / SAR {observed['partial_sar']:,.0f} partial.",
                }

        # Fallback: business-level recovered-value delta (coarse; explicitly scoped).
        audit = await get_latest_money_audit(self.session, self.business_id)
        if not audit:
            return {"verified": False, "attribution_scope": "business", "note": "No audit to verify against"}
        recovered = float(audit.get("money_recovered_sar") or 0)
        baseline = float((context or {}).get("baseline_recovered_sar") or 0)
        delta = round(recovered - baseline, 2)

        if delta > 0:
            await record_impact(
                self.session,
                self.business_id,
                "money_recovered",
                delta,
                baseline_sar=baseline,
                actual_sar=recovered,
                verified=True,
                verification="observed",
                attribution="business_level",  # §5: coarse, never presented as per-action
                evidence={"money_audit_id": audit.get("id")},
                source="agent",
                commit=False,
            )
        return {
            "verified": recovered >= baseline,
            "attribution_scope": "business",
            "actual_recovered_sar": recovered,
            "delta_sar": delta,
            "note": f"Business-level money_recovered delta = SAR {delta:,.0f} (baseline {baseline:,.0f}); not attributable to a single action.",
        }

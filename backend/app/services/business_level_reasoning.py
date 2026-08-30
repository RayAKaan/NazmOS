"""V8 Business-Level AI Reasoning — the highest-value AI use.

At each audit, give AI a structured summary of the business:
  - inventory exposure
  - top risks
  - fast movers
  - dead stock
  - seasonal inventory
  - stockout risks
  - margin problems
  - supplier constraints
  - cash constraints
  - previous actions
  - previous outcomes

Ask: "What are the three most important decisions this owner should make this week?"

The AI must prioritize existing validated opportunities.
It must not invent new financial findings.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.services.evidence_package import ItemEvidence, BusinessContext, AuditEvidencePackage
from app.services.outcome_tracker import OutcomeTracker, OutcomeRecord

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a business-level financial advisor for a Saudi retail store owner.

Your role: analyze the structured business summary and identify the THREE most important decisions the owner should make this week.

ABSOLUTE RULES:
1. You MUST ONLY use the facts provided in the business summary.
2. You MUST NOT invent any financial numbers not provided.
3. You MUST NOT invent any evidence not provided.
4. You MUST prioritize existing validated opportunities.
5. You MUST cite which data points support each recommendation.
6. You MUST return ONLY valid JSON matching the required schema.
7. You MUST consider owner constraints (cash budget, blocked products, strategic items).
8. You MUST distinguish between urgent actions and monitoring.

DECISION PRIORITIES:
1. Money that can be recovered NOW (dead stock with discount potential)
2. Money that will be lost SOON (stockout risk on fast movers)
3. Money that is being wasted (margin leakage, overstock)
4. Strategic decisions (seasonal preparation, supplier changes)

Your output MUST be a single JSON object:

{
  "top_decisions": [
    {
      "priority": 1,
      "sku": "SKU code",
      "product_name": "Product name",
      "decision": "DO_NOTHING" | "REORDER" | "TRANSFER" | "DISCOUNT" | "PRICE_CHANGE" | "RECOVERY_MATCH" | "MANUAL_REVIEW",
      "why": "Plain explanation of why this matters",
      "financial_exposure_sar": 0.0,
      "recoverable_range_sar": "SAR X - SAR Y",
      "confidence": 0.0 to 1.0,
      "urgency": "immediate" | "this_week" | "this_month" | "monitor",
      "evidence_cited": ["field1", "field2"],
      "what_could_make_this_wrong": "Risk factors that could invalidate this recommendation"
    }
  ],
  "business_health": {
    "overall": "healthy" | "needs_attention" | "critical",
    "total_exposure_sar": 0.0,
    "top_risk": "description",
    "top_opportunity": "description"
  },
  "summary": "2-3 sentence plain explanation for the owner"
}
"""


@dataclass
class BusinessLevelDecision:
    """One of the top 3 business decisions."""
    priority: int
    sku: str
    product_name: str
    decision: str
    why: str
    financial_exposure_sar: float
    recoverable_range_sar: str
    confidence: float
    urgency: str
    evidence_cited: list[str]
    what_could_make_this_wrong: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


@dataclass
class BusinessLevelResult:
    """Result of business-level AI reasoning."""
    top_decisions: list[BusinessLevelDecision] = field(default_factory=list)
    business_health: dict[str, str] = field(default_factory=dict)
    summary: str = ""
    latency_ms: float = 0
    is_valid: bool = True
    validation_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "top_decisions": [d.to_dict() for d in self.top_decisions],
            "business_health": self.business_health,
            "summary": self.summary,
            "latency_ms": self.latency_ms,
            "is_valid": self.is_valid,
            "validation_errors": self.validation_errors,
        }


def _build_business_summary_prompt(
    package: AuditEvidencePackage,
    historical_outcomes: list[OutcomeRecord] | None = None,
) -> str:
    """Build the prompt for business-level reasoning."""
    parts = []

    # Business context
    b = package.business
    parts.append(f"## Business: {b.business_id} ({b.business_type})")
    parts.append(f"- Total inventory value: SAR {b.total_inventory_value_sar}")
    parts.append(f"- Total capital at risk: SAR {b.total_capital_at_risk_sar}")
    parts.append(f"- Total recoverable: SAR {b.total_recoverable_high_sar}")
    if b.cash_budget:
        parts.append(f"- Cash budget: SAR {b.cash_budget}")
    if b.max_discount_pct:
        parts.append(f"- Max discount: {b.max_discount_pct}%")
    if b.blocked_discount_products:
        parts.append(f"- Discount blocked for: {', '.join(b.blocked_discount_products)}")
    if b.strategic_products:
        parts.append(f"- Strategic products: {', '.join(b.strategic_products)}")

    # Classification summary
    classification_counts: dict[str, int] = {}
    for item in package.items:
        cls = item.classification
        classification_counts[cls] = classification_counts.get(cls, 0) + 1
    parts.append(f"\n## Inventory Classification Summary")
    for cls, count in sorted(classification_counts.items()):
        parts.append(f"- {cls}: {count} items")

    # Top items by financial exposure
    sorted_items = sorted(package.items, key=lambda x: x.inventory_value_sar, reverse=True)
    parts.append(f"\n## Top Items by Financial Exposure")
    for item in sorted_items[:10]:
        parts.append(
            f"- {item.sku} ({item.product_name}): {item.classification}, "
            f"SAR {item.inventory_value_sar} value, "
            f"{item.daily_velocity:.1f}/day velocity, "
            f"{item.days_of_supply or 'N/A'} days supply"
        )

    # Dead stock
    dead_items = [i for i in package.items if i.classification == "DEAD" and i.current_stock > 0]
    if dead_items:
        parts.append(f"\n## Dead Stock ({len(dead_items)} items)")
        for item in dead_items:
            parts.append(
                f"- {item.sku} ({item.product_name}): {item.current_stock} units, "
                f"SAR {item.inventory_value_sar}, "
                f"{item.days_since_last_sale or 'N/A'} days since last sale"
            )

    # Stockout risk
    stockout_items = [i for i in package.items if i.stockout_days is not None]
    if stockout_items:
        parts.append(f"\n## Stockout Risk ({len(stockout_items)} items)")
        for item in stockout_items:
            parts.append(
                f"- {item.sku} ({item.product_name}): {item.current_stock} units, "
                f"{item.days_of_supply or 'N/A'} days supply, "
                f"{item.daily_velocity:.1f}/day velocity"
            )

    # Margin issues
    low_margin = [i for i in package.items if i.margin_pct is not None and i.margin_pct < 0.15]
    if low_margin:
        parts.append(f"\n## Margin Issues ({len(low_margin)} items)")
        for item in low_margin:
            parts.append(
                f"- {item.sku} ({item.product_name}): {item.margin_pct:.1%} margin, "
                f"SAR {item.cost_price_sar} cost, SAR {item.sell_price_sar} sell"
            )

    # Historical outcomes
    if historical_outcomes:
        parts.append(f"\n## Historical Outcomes (recent)")
        for outcome in historical_outcomes[-10:]:
            parts.append(
                f"- {outcome.action_type} on {outcome.sku}: "
                f"predicted SAR {outcome.expected_recovery_sar or 'N/A'}, "
                f"actual SAR {outcome.actual_recovery_sar}"
            )

    parts.append(f"\n## Question")
    parts.append(f"What are the THREE most important decisions this owner should make this week?")
    parts.append(f"Return ONLY the JSON response.")

    return "\n".join(parts)


def _parse_business_level_response(response_text: str, latency_ms: float) -> BusinessLevelResult:
    """Parse and validate business-level AI response."""
    errors = []
    text = response_text.strip()

    # Handle markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        json_lines = [l for l in lines[1:] if not l.startswith("```")]
        text = "\n".join(json_lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{.*"top_decisions".*\}', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return BusinessLevelResult(
                    latency_ms=latency_ms,
                    is_valid=False,
                    validation_errors=["Could not parse AI response as JSON"],
                )
        else:
            return BusinessLevelResult(
                latency_ms=latency_ms,
                is_valid=False,
                validation_errors=["No JSON found in AI response"],
            )

    # Parse top decisions
    decisions = []
    valid_decisions = {"DO_NOTHING", "REORDER", "TRANSFER", "DISCOUNT", "PRICE_CHANGE", "RECOVERY_MATCH", "MANUAL_REVIEW"}
    for d in data.get("top_decisions", [])[:3]:
        decision = d.get("decision", "MANUAL_REVIEW")
        if decision not in valid_decisions:
            errors.append(f"Invalid decision: {decision}")
            decision = "MANUAL_REVIEW"

        confidence = d.get("confidence", 0.0)
        try:
            confidence = float(confidence)
            if not (0.0 <= confidence <= 1.0):
                errors.append(f"Confidence out of range: {confidence}")
                confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.0

        decisions.append(BusinessLevelDecision(
            priority=d.get("priority", 1),
            sku=d.get("sku", "UNKNOWN"),
            product_name=d.get("product_name", "Unknown"),
            decision=decision,
            why=d.get("why", ""),
            financial_exposure_sar=d.get("financial_exposure_sar", 0.0),
            recoverable_range_sar=d.get("recoverable_range_sar", "N/A"),
            confidence=confidence,
            urgency=d.get("urgency", "monitor"),
            evidence_cited=d.get("evidence_cited", []),
            what_could_make_this_wrong=d.get("what_could_make_this_wrong", ""),
        ))

    return BusinessLevelResult(
        top_decisions=decisions,
        business_health=data.get("business_health", {}),
        summary=data.get("summary", ""),
        latency_ms=latency_ms,
        is_valid=len(errors) == 0,
        validation_errors=errors,
    )


async def reason_about_business(
    package: AuditEvidencePackage,
    llm_caller: Any,
    *,
    historical_outcomes: list[OutcomeRecord] | None = None,
) -> BusinessLevelResult:
    """Call AI to reason about the top 3 business decisions.

    This is the highest-value AI use — business-level prioritization.
    """
    start = time.monotonic()

    prompt = _build_business_summary_prompt(package, historical_outcomes)

    try:
        response_text = await llm_caller(SYSTEM_PROMPT, prompt)
    except Exception as e:
        logger.warning("Business-level AI reasoning failed: %s", e)
        return BusinessLevelResult(
            latency_ms=(time.monotonic() - start) * 1000,
            is_valid=False,
            validation_errors=[f"AI call failed: {e}"],
        )

    latency_ms = (time.monotonic() - start) * 1000
    return _parse_business_level_response(response_text, latency_ms)

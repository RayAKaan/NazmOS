"""V8 AI Contextual Reasoning Service.

The AI is a reasoning layer ABOVE the deterministic financial engine.
It does NOT calculate financial truth. It reasons about ambiguity using evidence.

Architecture:
  EVIDENCE PACKAGE (deterministic facts)
      → AI REASONING (contextual judgment)
      → STRUCTURED OUTPUT (JSON)
      → VALIDATION (backend checks every field)
      → CONSTRAINT ENGINE (owner rules)
      → FALLBACK (deterministic if AI fails)

Absolute rules:
  - AI never invents SAR values
  - AI never invents evidence
  - AI never bypasses constraints
  - AI never accesses another tenant
  - AI only receives the structured evidence package
  - AI confidence is NOT financial recovery confidence
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.services.evidence_package import ItemEvidence, BusinessContext, AuditEvidencePackage

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a financial decision reasoning assistant for a Saudi retail business.

Your role: resolve ambiguity in inventory classification and recommend actions based on provided evidence.

ABSOLUTE RULES:
1. You MUST ONLY use the facts provided in the evidence package.
2. You MUST NOT invent any financial numbers (SAR values, quantities, percentages).
3. You MUST NOT invent any evidence not provided.
4. You MUST NOT assume future demand, prices, or outcomes.
5. You MUST cite which evidence fields support your reasoning.
6. You MUST return ONLY valid JSON matching the required schema.
7. If evidence is insufficient, return "INSUFFICIENT_EVIDENCE".

Your output MUST be a single JSON object with exactly these fields:

{
  "decision": "DO_NOTHING" | "REORDER" | "TRANSFER" | "DISCOUNT" | "PRICE_CHANGE" | "RECOVERY_MATCH" | "MANUAL_REVIEW",
  "confidence": 0.0 to 1.0,
  "reasoning": "string citing specific evidence fields",
  "evidence_ids": ["list of evidence fields you used"],
  "risk_flags": ["list of risks or empty"],
  "recommended_action": {
    "action_type": "string matching decision",
    "priority": 1-3,
    "quantity": number or null,
    "discount_pct": number or null,
    "notes": "string"
  } or null
}

DECISION OPTIONS:
- DO_NOTHING: Item is fine, no action needed
- REORDER: Need to restock or purchase more
- TRANSFER: Move inventory between branches
- DISCOUNT: Reduce price to clear inventory
- PRICE_CHANGE: Adjust pricing (increase or decrease)
- RECOVERY_MATCH: Match with a buyer/partner
- MANUAL_REVIEW: Insufficient data, human must decide

You are reasoning about AMBIGUOUS cases. Clear cases (dead stock, fast movers) don't need your input.
Focus on:
- Seasonal vs dead: is demand seasonal or permanently gone?
- Growth vs overstock: is increasing inventory justified by demand?
- Promotion vs structural margin leakage
- Strategic inventory vs dead inventory
- Reorder vs do nothing: is the timing right?
- Discount vs transfer: which recovers more value?
"""

RESPONSE_SCHEMA = """{
  "decision": "DO_NOTHING",
  "confidence": 0.85,
  "reasoning": "Based on evidence...",
  "evidence_ids": ["classification", "monthly_concentration_peak", "days_of_supply"],
  "risk_flags": [],
  "recommended_action": null
}"""


@dataclass
class AIReasoningResult:
    """Structured output from AI reasoning."""
    decision: str
    confidence: float
    reasoning: str
    evidence_ids: list[str]
    risk_flags: list[str]
    recommended_action: dict[str, Any] | None
    raw_response: str = ""
    latency_ms: float = 0
    tokens_used: int = 0
    is_valid: bool = True
    validation_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "evidence_ids": self.evidence_ids,
            "risk_flags": self.risk_flags,
            "recommended_action": self.recommended_action,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "is_valid": self.is_valid,
            "validation_errors": self.validation_errors,
        }


VALID_DECISIONS = {"DO_NOTHING", "REORDER", "TRANSFER", "DISCOUNT", "PRICE_CHANGE", "RECOVERY_MATCH", "MANUAL_REVIEW"}


def _build_reasoning_prompt(item: ItemEvidence, business: BusinessContext) -> str:
    """Build the user prompt for AI reasoning about one item."""
    prompt_parts = [
        f"## Item Evidence: {item.sku} ({item.product_name})",
        f"- Classification: {item.classification}",
        f"- Current stock: {item.current_stock} units",
        f"- Cost: SAR {item.cost_price_sar}/unit",
        f"- Sell price: SAR {item.sell_price_sar}/unit",
        f"- Inventory value: SAR {item.inventory_value_sar}",
        f"- Daily velocity: {item.daily_velocity} units/day",
        f"- Recent 30-day velocity: {item.recent_velocity_per_day} units/day",
        f"- Prior 30-day velocity: {item.prior_velocity_per_day} units/day",
    ]

    if item.days_of_supply is not None:
        prompt_parts.append(f"- Days of supply: {item.days_of_supply}")
    if item.days_since_last_sale is not None:
        prompt_parts.append(f"- Days since last sale: {item.days_since_last_sale}")
    if item.inventory_age_days is not None:
        prompt_parts.append(f"- Inventory age: {item.inventory_age_days} days")
    if item.monthly_concentrations:
        prompt_parts.append(f"- Monthly sales (recent months): {item.monthly_concentrations}")
    if item.monthly_concentration_peak is not None:
        prompt_parts.append(f"- Monthly concentration peak: {item.monthly_concentration_peak:.1%}")
    if item.supplier_name:
        prompt_parts.append(f"- Supplier: {item.supplier_name}")
    if item.supplier_lead_time_days is not None:
        prompt_parts.append(f"- Supplier lead time: {item.supplier_lead_time_days} days")
    if item.supplier_moq is not None:
        prompt_parts.append(f"- Supplier MOQ: SAR {item.supplier_moq}")
    if item.confirmed_inbound_qty > 0:
        prompt_parts.append(f"- Confirmed inbound: {item.confirmed_inbound_qty} units")

    prompt_parts.append(f"\n## Financial Exposure")
    prompt_parts.append(f"- Capital at risk: SAR {item.capital_at_risk_sar}")
    prompt_parts.append(f"- Revenue at risk: SAR {item.revenue_at_risk_sar}")
    prompt_parts.append(f"- Gross profit at risk: SAR {item.gross_profit_at_risk_sar}")
    prompt_parts.append(f"- Recoverable range: SAR {item.recoverable_low_sar} - SAR {item.recoverable_high_sar}")

    if item.overstock_days:
        prompt_parts.append(f"- OVERSTOCK: {item.overstock_days:.0f} days of supply (exceeds 60-day threshold)")
    if item.stockout_days:
        prompt_parts.append(f"- STOCKOUT RISK: {item.stockout_days:.0f} days of supply (below 7-day threshold)")
    if item.margin_pct is not None:
        prompt_parts.append(f"- Current margin: {item.margin_pct:.1%} (target: {item.target_margin_pct:.0%})")

    prompt_parts.append(f"\n## Candidate Actions")
    prompt_parts.append(f"- Actions considered: {', '.join(item.candidate_actions) if item.candidate_actions else 'none'}")

    if item.is_strategic:
        prompt_parts.append(f"- NOTE: This is a STRATEGIC product. Owner may have restrictions on discounting.")

    # Business constraints
    prompt_parts.append(f"\n## Business Context")
    prompt_parts.append(f"- Cash budget: SAR {business.cash_budget}" if business.cash_budget else "- Cash budget: not specified")
    if business.max_discount_pct is not None:
        prompt_parts.append(f"- Max discount allowed: {business.max_discount_pct:.0f}%")
    if business.blocked_discount_products:
        prompt_parts.append(f"- Discount blocked for: {', '.join(business.blocked_discount_products)}")

    # Historical outcomes (MODE C only)
    if item.historical_outcomes:
        prompt_parts.append(f"\n## Historical Outcomes (similar actions)")
        for outcome in item.historical_outcomes[-5:]:
            prompt_parts.append(f"- {outcome.get('action_type', '?')}: recovered SAR {outcome.get('actual_recovery_sar', 0)} (predicted SAR {outcome.get('expected_recovery_sar', 0)})")

    prompt_parts.append(f"\n## Question")
    prompt_parts.append(f"What is the best action for this item? Consider the classification, financial exposure, and any ambiguity.")
    prompt_parts.append(f"Return ONLY the JSON response.")

    return "\n".join(prompt_parts)


async def reason_about_item(
    item: ItemEvidence,
    business: BusinessContext,
    llm_caller: Any,
    *,
    include_historical: bool = False,
) -> AIReasoningResult:
    """Call AI to reason about one ambiguous item.

    Args:
        item: Structured evidence for the item
        business: Business context with constraints
        llm_caller: Async callable that sends prompt to LLM and returns response text
        include_historical: Whether to include historical outcomes (MODE C)

    Returns:
        AIReasoningResult with structured decision
    """
    start = time.monotonic()

    prompt = _build_reasoning_prompt(item, business)

    try:
        response_text = await llm_caller(SYSTEM_PROMPT, prompt)
    except Exception as e:
        logger.warning("AI reasoning call failed for %s: %s", item.sku, e)
        return AIReasoningResult(
            decision="MANUAL_REVIEW",
            confidence=0.0,
            reasoning=f"AI call failed: {e}",
            evidence_ids=[],
            risk_flags=["AI_UNAVAILABLE"],
            recommended_action=None,
            raw_response="",
            latency_ms=(time.monotonic() - start) * 1000,
            is_valid=False,
            validation_errors=[f"AI call failed: {e}"],
        )

    latency_ms = (time.monotonic() - start) * 1000

    # Parse and validate
    result = _parse_ai_response(response_text, latency_ms)
    return result


def _parse_ai_response(response_text: str, latency_ms: float) -> AIReasoningResult:
    """Parse and validate AI response into structured result."""
    errors: list[str] = []

    # Extract JSON from response
    text = response_text.strip()
    # Handle markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        json_lines = [l for l in lines[1:] if not l.startswith("```")]
        text = "\n".join(json_lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON in the response
        import re
        match = re.search(r'\{[^{}]*"decision"[^{}]*\}', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return AIReasoningResult(
                    decision="MANUAL_REVIEW",
                    confidence=0.0,
                    reasoning="AI returned unparseable response",
                    evidence_ids=[],
                    risk_flags=["INVALID_OUTPUT"],
                    recommended_action=None,
                    raw_response=response_text,
                    latency_ms=latency_ms,
                    is_valid=False,
                    validation_errors=["Could not parse AI response as JSON"],
                )
        else:
            return AIReasoningResult(
                decision="MANUAL_REVIEW",
                confidence=0.0,
                reasoning="AI returned unparseable response",
                evidence_ids=[],
                risk_flags=["INVALID_OUTPUT"],
                recommended_action=None,
                raw_response=response_text,
                latency_ms=latency_ms,
                is_valid=False,
                validation_errors=["No JSON found in AI response"],
            )

    # Validate decision
    decision = data.get("decision", "MANUAL_REVIEW")
    if decision not in VALID_DECISIONS:
        errors.append(f"Invalid decision: {decision}")
        decision = "MANUAL_REVIEW"

    # Validate confidence
    confidence = data.get("confidence", 0.0)
    try:
        confidence = float(confidence)
        if not (0.0 <= confidence <= 1.0):
            errors.append(f"Confidence out of range: {confidence}")
            confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        errors.append(f"Invalid confidence: {confidence}")
        confidence = 0.0

    # Validate reasoning
    reasoning = data.get("reasoning", "")
    if not isinstance(reasoning, str) or len(reasoning) < 10:
        errors.append("Reasoning too short or missing")
        reasoning = reasoning if isinstance(reasoning, str) else str(reasoning)

    # Validate evidence_ids
    evidence_ids = data.get("evidence_ids", [])
    if not isinstance(evidence_ids, list):
        errors.append("evidence_ids must be a list")
        evidence_ids = []

    # Validate risk_flags
    risk_flags = data.get("risk_flags", [])
    if not isinstance(risk_flags, list):
        errors.append("risk_flags must be a list")
        risk_flags = []

    # Validate recommended_action
    recommended_action = data.get("recommended_action")
    if recommended_action is not None:
        if not isinstance(recommended_action, dict):
            errors.append("recommended_action must be a dict or null")
            recommended_action = None

    is_valid = len(errors) == 0
    if errors:
        logger.warning("AI response validation errors: %s", errors)

    return AIReasoningResult(
        decision=decision,
        confidence=confidence,
        reasoning=reasoning,
        evidence_ids=evidence_ids,
        risk_flags=risk_flags,
        recommended_action=recommended_action,
        raw_response=response_text,
        latency_ms=latency_ms,
        tokens_used=0,
        is_valid=is_valid,
        validation_errors=errors,
    )

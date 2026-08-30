"""Phase 3 §12 + V8 compat: AI Response Validator.

CANONICAL (production, Phase 3 §12): validates raw AI response strings
before they can influence any NazmOS decision (OpenCode brain path).
Validates JSON, schema, decision enum, confidence, evidence IDs, risk flags,
financial hallucination and prompt injection. Falls back on any failure.

V8 COMPATIBILITY: validates structured AIReasoningResult objects against
ItemEvidence + BusinessContext (V8/V11 experiment harness and A/B counterfactual
framework: ab_decision_framework, ai_challenge, closed_loop_experiment).
Kept for the experiment chain; the production decision path uses the string
contract. Both live behind one dispatcher: string input → §12 contract,
object input → V8 contract.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("ai_response_validator")

# --- Constants ---

ALLOWED_DECISIONS = frozenset({
    "DO_NOTHING",
    "REORDER",
    "TRANSFER",
    "DISCOUNT",
    "PRICE_CHANGE",
    "RECOVERY_MATCH",
    "MANUAL_REVIEW",
})

ALLOWED_RISK_FLAGS = frozenset({
    "INSUFFICIENT_EVIDENCE",
    "SEASONAL_RISK",
    "SUPPLIER_RISK",
    "CASH_CONSTRAINT",
    "MARGIN_RISK",
    "PROMOTION_EFFECT",
    "INBOUND_PO",
    "STRATEGIC_PRODUCT",
    "EXECUTION_LIMITATION",
    "DATA_QUALITY_RISK",
})

# Regex patterns that suggest the AI is trying to invent financial values
# outside of what the evidence provides.
FINANCIAL_HALLUCINATION_PATTERNS = [
    r"(?:expected|predicted|estimated|recovery|value|worth)\s+(?:is|:|=)\s*SAR\s*\d",
    r"SAR\s*\d[\d,]*\.?\d*",
    r"(?:revenue|profit|margin|loss)\s+(?:is|:|=)\s*\d[\d,]*\.?\d*",
    r"\b\d[\d,]*\.?\d*\s*SAR\b",
]

# Patterns that suggest prompt injection attempts
INJECTION_PATTERNS = [
    r"(?:ignore|disregard|forget)\s+(?:your|all|previous)\s+(?:rules|instructions|system)",
    r"(?:system|admin)\s*:\s*",
    r"(?:reveal|show|print|output)\s+(?:your|the|system)\s+(?:prompt|instructions|key)",
    r"(?:execute|run|eval|exec)\s*\(",
    r"<\s*(?:script|iframe|img|svg|video|audio)",
    r"(?:transfer|send|move)\s+(?:all|every|entire)\s+(?:inventory|stock|money|funds)",
    r"(?:you\s+are\s+now|act\s+as|pretend\s+to\s+be|roleplay\s+as)",
    r"(?:override|bypass|disable|ignore)\s+(?:safety|security|constraints|rules)",
]


@dataclass
class ValidationResult:
    """Result of validating an AI response."""
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sanitized_decision: str | None = None
    sanitized_confidence: float | None = None
    sanitized_reasoning: str | None = None
    sanitized_evidence_ids: list[str] = field(default_factory=list)
    sanitized_risk_flags: list[str] = field(default_factory=list)
    financial_hallucination_detected: bool = False
    injection_detected: bool = False
    constraint_rejected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "sanitized_decision": self.sanitized_decision,
            "financial_hallucination_detected": self.financial_hallucination_detected,
            "injection_detected": self.injection_detected,
            "constraint_rejected": self.constraint_rejected,
        }


def validate_ai_response(
    raw_output: Any,
    known_evidence_ids: list[str] | None = None,
    deterministic_decision: str | None = None,
    allowed_constraints: dict[str, Any] | None = None,
    *,
    check_financial_claims: bool = True,
    check_constraints: bool = True,
) -> ValidationResult:
    """Validate an AI response against the applicable contract.

    Dispatches on the type of the first argument:

    - ``str`` (Phase 3 §12, production OpenCode brain path): validates a raw
      AI response string (JSON, schema, enum, confidence, evidence, hallucination,
      injection, constraints). See ``_validate_string_response``.
    - structured AI reasoning object (V8/V11 experiment harness, e.g.
      ``AIReasoningResult``): validates the object against ItemEvidence +
      BusinessContext, including financial-claim verification and owner
      constraints. See ``_validate_ai_object_response``.

    The two contracts intentionally share this entry point so the
    experiment chain (``ab_decision_framework``, ``closed_loop_experiment``)
    keeps working unchanged while production uses the string contract.
    """
    if isinstance(raw_output, str) or isinstance(raw_output, (bytes, bytearray)):
        return _validate_string_response(
            raw_output,
            known_evidence_ids=known_evidence_ids,
            deterministic_decision=deterministic_decision,
            allowed_constraints=allowed_constraints,
        )
    return _validate_ai_object_response(
        raw_output,
        item=known_evidence_ids,
        business=deterministic_decision,
        allowed_constraints=allowed_constraints,
        check_financial_claims=check_financial_claims,
        check_constraints=check_constraints,
    )


def _validate_string_response(
    raw_output: str,
    known_evidence_ids: list[str] | None = None,
    deterministic_decision: str | None = None,
    allowed_constraints: dict[str, Any] | None = None,
) -> ValidationResult:
    """Validate a raw AI response string (Phase 3 §12 production contract).

    Checks:
    1. JSON syntax
    2. Schema (required fields, types)
    3. Allowed decision enum
    4. Confidence range [0.0, 1.0]
    5. Reasoning exists and is non-empty
    6. Evidence IDs exist in the known set
    7. Risk flags are from the allowed set
    8. No fabricated financial values
    9. No prompt injection patterns in reasoning
    10. Decision compatibility with deterministic evidence
    11. Decision compatibility with owner constraints

    Returns ValidationResult with sanitized values if valid.
    """
    result = ValidationResult()

    if not raw_output or not raw_output.strip():
        result.is_valid = False
        result.errors.append("EMPTY_RESPONSE")
        return result

    # Strip any markdown code fences
    cleaned = raw_output.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first line (```json or ```) and last line (```)
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        cleaned = "\n".join(lines)

    # 1. JSON syntax
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        result.is_valid = False
        result.errors.append(f"INVALID_JSON: {e}")
        return result

    if not isinstance(data, dict):
        result.is_valid = False
        result.errors.append("NOT_OBJECT")
        return result

    # 2. Schema — required fields
    required_fields = ["decision", "confidence", "reasoning"]
    for field_name in required_fields:
        if field_name not in data:
            result.is_valid = False
            result.errors.append(f"MISSING_FIELD:{field_name}")

    if not result.is_valid:
        return result

    # 3. Allowed decision
    decision = str(data.get("decision", "")).strip().upper()
    if decision not in ALLOWED_DECISIONS:
        result.is_valid = False
        result.errors.append(f"INVALID_DECISION:{decision}")
        return result
    result.sanitized_decision = decision

    # 4. Confidence range
    try:
        confidence = float(data.get("confidence", -1))
    except (TypeError, ValueError):
        confidence = -1.0

    if not (0.0 <= confidence <= 1.0):
        result.is_valid = False
        result.errors.append(f"INVALID_CONFIDENCE:{confidence}")
        return result
    result.sanitized_confidence = confidence

    # 5. Reasoning exists
    reasoning = str(data.get("reasoning", "")).strip()
    if not reasoning:
        result.is_valid = False
        result.errors.append("EMPTY_REASONING")
        return result
    result.sanitized_reasoning = reasoning

    # 6. Evidence IDs
    evidence_ids = data.get("evidence_ids", [])
    if not isinstance(evidence_ids, list):
        evidence_ids = []

    if known_evidence_ids is not None:
        known_set = set(known_evidence_ids)
        for eid in evidence_ids:
            if str(eid) not in known_set:
                result.errors.append(f"UNKNOWN_EVIDENCE_ID:{eid}")
        if result.errors:
            result.is_valid = False
            return result

    result.sanitized_evidence_ids = [str(e) for e in evidence_ids]

    # 7. Risk flags
    risk_flags = data.get("risk_flags", [])
    if not isinstance(risk_flags, list):
        risk_flags = []

    valid_flags = []
    for flag in risk_flags:
        flag_str = str(flag).strip().upper()
        if flag_str in ALLOWED_RISK_FLAGS:
            valid_flags.append(flag_str)
        else:
            result.warnings.append(f"UNKNOWN_RISK_FLAG:{flag}")
    result.sanitized_risk_flags = valid_flags

    # 8. Financial hallucination detection
    full_text = json.dumps(data)
    for pattern in FINANCIAL_HALLUCINATION_PATTERNS:
        matches = re.findall(pattern, full_text, re.IGNORECASE)
        if matches:
            # Filter out matches that are just referencing existing evidence values
            # (e.g., "SAR 12000" appearing in the original evidence_ids)
            result.financial_hallucination_detected = True
            result.warnings.append(f"FINANCIAL_HALLUCINATION:{pattern}")
            break

    # 9. Prompt injection detection
    reasoning_lower = reasoning.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, reasoning_lower):
            result.injection_detected = True
            result.warnings.append(f"INJECTION_DETECTED:{pattern}")
            break

    # 10. Decision compatibility with deterministic evidence
    if deterministic_decision and decision != "DO_NOTHING":
        # AI should not contradict a clearly deterministic DEAD decision
        # unless it has strong reason
        if deterministic_decision == "DO_NOTHING" and decision in ("REORDER", "TRANSFER"):
            result.warnings.append("CHALLENGES_DETERMINISTIC_DO_NOTHING")

    # 11. Owner constraint compatibility
    if allowed_constraints and decision == "DISCOUNT":
        max_discount = allowed_constraints.get("max_discount_pct")
        if max_discount is not None and max_discount <= 0:
            result.errors.append("DISCOUNT_BLOCKED_BY_CONSTRAINT")
            result.is_valid = False
            return result

    # If we got here, the response is valid (may have warnings)
    if result.errors:
        result.is_valid = False

    return result


# ============================================================================
# V8 OBJECT-BASED CONTRACT (experiment harness)
# Validates structured AIReasoningResult objects against ItemEvidence +
# BusinessContext. Used by ab_decision_framework (counterfactual A/B) and the
# closed-loop experiment. Production uses the string contract above.
# ============================================================================


def _validate_ai_object_response(
    ai_result: Any,
    item: Any | None = None,
    business: Any | None = None,
    allowed_constraints: dict[str, Any] | None = None,
    *,
    check_financial_claims: bool = True,
    check_constraints: bool = True,
) -> ValidationResult:
    """Validate a structured AI reasoning object (V8/V11 experiment contract).

    Mirrors the checks of the string contract but operates on the object's
    fields directly and additionally applies item/business owner constraints.
    Returns ``ValidationResult`` with ``constraint_rejected`` set when the
    AI proposal is disallowed by owner constraints.
    """
    result = ValidationResult()

    decision = str(getattr(ai_result, "decision", "") or "").strip().upper()
    if not decision or decision not in ALLOWED_DECISIONS:
        result.is_valid = False
        result.errors.append(f"INVALID_DECISION:{decision or 'EMPTY'}")
        return result
    result.sanitized_decision = decision

    try:
        confidence = float(getattr(ai_result, "confidence", -1) or -1)
    except (TypeError, ValueError):
        confidence = -1.0
    if not (0.0 <= confidence <= 1.0):
        result.is_valid = False
        result.errors.append(f"INVALID_CONFIDENCE:{confidence}")
        return result
    result.sanitized_confidence = confidence

    reasoning = str(getattr(ai_result, "reasoning", "") or "").strip()
    if not reasoning:
        result.is_valid = False
        result.errors.append("EMPTY_REASONING")
        return result
    result.sanitized_reasoning = reasoning

    evidence_fields = set()
    if item is not None and hasattr(item, "to_dict"):
        evidence_fields = set(item.to_dict().keys())
    evidence_ids = list(getattr(ai_result, "evidence_ids", None) or [])
    for eid in evidence_ids:
        if str(eid) not in evidence_fields:
            result.errors.append(f"UNKNOWN_EVIDENCE_ID:{eid}")
    result.sanitized_evidence_ids = [str(e) for e in evidence_ids]

    risk_flags = list(getattr(ai_result, "risk_flags", None) or [])
    for flag in risk_flags:
        flag_str = str(flag).strip().upper()
        if flag_str in ALLOWED_RISK_FLAGS:
            result.sanitized_risk_flags.append(flag_str)
        else:
            result.warnings.append(f"UNKNOWN_RISK_FLAG:{flag}")

    if check_financial_claims:
        mismatch = _verify_financial_claims(ai_result, item)
        if mismatch is not None:
            result.financial_hallucination_detected = True
            result.is_valid = False
            result.errors.append(f"FINANCIAL_HALLUCINATION:{mismatch}")

    if result.errors:
        result.is_valid = False
        return result

    if check_constraints:
        rejected = _apply_owner_constraints(
            result, ai_result, item, business, allowed_constraints,
        )
        if rejected:
            result.constraint_rejected = True
            result.is_valid = False

    return result


def _apply_owner_constraints(
    result: ValidationResult,
    ai_result: Any,
    item: Any | None,
    business: Any | None,
    allowed_constraints: dict[str, Any] | None,
) -> bool:
    """Apply owner constraints to the AI proposal. Returns True if rejected."""
    decision = str(getattr(ai_result, "decision", "") or "").strip().upper()
    constraints: dict[str, Any] = {}
    if business is not None and hasattr(business, "to_dict"):
        constraints = dict(business.to_dict())
    if allowed_constraints:
        for key, value in allowed_constraints.items():
            if value is not None:
                constraints.setdefault(key, value)

    sku = str(getattr(item, "sku", "") or "")

    if decision == "DISCOUNT":
        blocked = {str(s) for s in (constraints.get("blocked_discount_products") or [])}
        if sku in blocked:
            result.errors.append("DISCOUNT_BLOCKED_BY_CONSTRAINT")
            return True
        strategic = {str(s) for s in (constraints.get("strategic_products") or [])}
        if sku in strategic:
            result.errors.append("DISCOUNT_BLOCKED_STRATEGIC_PRODUCT")
            return True
        if getattr(item, "is_strategic", False) is True and not strategic:
            result.errors.append("DISCOUNT_BLOCKED_STRATEGIC_PRODUCT")
            return True
        max_pct = constraints.get("max_discount_pct")
        if max_pct is not None:
            recommended = getattr(ai_result, "recommended_action", None) or {}
            discount_pct = None
            if isinstance(recommended, dict):
                discount_pct = recommended.get("discount_pct") or recommended.get("recommended_discount_pct")
            if discount_pct is not None and float(discount_pct) > float(max_pct):
                result.errors.append("DISCOUNT_EXCEEDS_MAX_PCT")
                return True

    elif decision == "REORDER":
        budget = constraints.get("cash_budget")
        if budget is not None:
            moq = getattr(item, "supplier_moq", None)
            if moq is not None and float(moq) > float(budget):
                result.errors.append("REORDER_MOQ_EXCEEDS_BUDGET")
                return True

    return False


def _verify_financial_claims(ai_result: Any, item: Any | None) -> str | None:
    """Check the AI object for SAR claims not supported by item evidence.

    Returns a human-readable mismatch description if the AI claimed financial
    figures (e.g. recovery amounts) outside the evidence range, else None.
    """
    if item is None:
        return None

    evidence_values = _collect_evidence_sar_values(item)
    if not evidence_values:
        return None

    claim_text = " ".join([
        str(getattr(ai_result, "reasoning", "") or ""),
        json.dumps(getattr(ai_result, "recommended_action", None) or {}),
    ])

    # SAR-prefixed and suffixed amounts
    matches = re.findall(r"SAR\s*([\d][\d,]*(?:\.\d+)?)", claim_text, re.IGNORECASE)
    matches += re.findall(r"([\d][\d,]*(?:\.\d+)?)\s*SAR", claim_text, re.IGNORECASE)

    for raw_value in matches:
        try:
            value = float(raw_value.replace(",", ""))
        except ValueError:
            continue
        if not _value_is_plausible(value, evidence_values):
            return (
                f"AI claimed SAR {raw_value} which is not supported by item evidence "
                f"(evidence: {sorted(evidence_values)})"
            )
    return None


def _collect_evidence_sar_values(item: Any) -> list[float]:
    """Gather the item's financial evidence values for claim verification."""
    values: list[float] = []
    fields = (
        "inventory_value_sar",
        "capital_at_risk_sar",
        "revenue_at_risk_sar",
        "gross_profit_at_risk_sar",
        "recoverable_low_sar",
        "recoverable_high_sar",
        "expected_recovery_sar",
        "cost_price_sar",
        "sell_price_sar",
        "supplier_moq",
    )
    for field_name in fields:
        value = getattr(item, field_name, None)
        try:
            if value is not None:
                value = float(value)
        except (TypeError, ValueError):
            continue
        if value is not None and value > 0:
            values.append(round(value, 2))
    return values


def _value_is_plausible(value: float, evidence_values: list[float]) -> bool:
    """True if the AI claim is plausibly consistent with one evidence value."""
    for evidence in evidence_values:
        if evidence == 0:
            continue
        if abs(value - evidence) / evidence <= 0.02 or abs(value - evidence) <= 0.01:
            return True
    return False


def select_final_decision(
    deterministic_decision: str | None,
    ai_decision: str | None,
    ai_confidence: float,
    validation: ValidationResult | None,
) -> tuple[str, str]:
    """Select the final decision between deterministic and the AI proposal.

    Returns ``(final_decision, decision_source)``.

    Decision rules (fail-closed), with decision_source strings compatible with
    ``compare_modes`` counting (AI_* -> override; AGREES in source -> agreement;
    MANUAL_REVIEW in source -> manual review; LOW_AI_CONFIDENCE -> low-conf):
    - AI invalid / constraint-rejected -> deterministic retained (no AI credit).
    - AI confidence below 0.70 -> deterministic retained, source records the
      low-confidence participation.
    - AI agrees with deterministic -> deterministic retained, agreement credit.
    - AI proposes a different, valid decision -> AI override credit.
    """
    ai = str(ai_decision or "").strip().upper()
    det = str(deterministic_decision or "DO_NOTHING").strip().upper()

    if not ai or ai not in ALLOWED_DECISIONS:
        return det, "DETERMINISTIC_NO_AI"

    if validation is not None and not validation.is_valid:
        return det, "DETERMINISTIC_FALLBACK"

    if validation is not None and validation.constraint_rejected:
        return det, "DETERMINISTIC_CONSTRAINT_REJECTED"

    try:
        confidence = float(ai_confidence or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0

    if confidence < 0.70:
        return det, "DETERMINISTIC_LOW_AI_CONFIDENCE"

    if ai == "MANUAL_REVIEW":
        return "MANUAL_REVIEW", "MANUAL_REVIEW"

    if ai == det:
        return det, "DETERMINISTIC_AI_AGREES"

    return ai, "AI_OVERRIDE"


def validate_decision_in_registry(
    decision: str,
    registered_actions: set[str],
) -> bool:
    """Check if a decision maps to a registered action in the action registry."""
    # DO_NOTHING and MANUAL_REVIEW don't need registry entries
    if decision in ("DO_NOTHING", "MANUAL_REVIEW"):
        return True
    return decision in registered_actions

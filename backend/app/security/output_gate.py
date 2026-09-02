"""Output gate: fail-closed validation of any AI response.

An AI response is un-trusted until it passes here. The gate enforces:

1. Integrity     – the capsule signature/hash must verify.
2. Freshness     – capsule must not be expired (replay protection).
3. Constraints   – JSON parseable; decision ∈ deterministic candidate set.
4. Evidence      – every evidence_id is a capsule signal / opaque ref.
5. No exact data – no SAR amount patterns (capsule carries no absolute values).
6. Injection     – prompt-injection patterns are rejected, not warned.
7. Size/time     – response size and elapsed time caps.
8. DLP           – credentialed/identifiable content is BLOCKED.

Any failure => ``is_allowed=False``; the caller MUST NOT act on the response.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.security.capsule import CapsuleSigner, ReasoningCapsule
from app.security.dlp import DLPViolation, DlpScanner
from app.services.ai_response_validator import INJECTION_PATTERNS as _INJECTION_PATTERNS

logger = logging.getLogger(__name__)

SAR_PATTERNS = [
    re.compile(r"SAR\s*\d[\d,]*\.?\d*", re.IGNORECASE),
    re.compile(r"\b\d[\d,]*\.?\d*\s*SAR\b", re.IGNORECASE),
]

# Broader, fail-closed injection rules: the shared validator's set is tuned for
# single-adjective phrases; the output gate adds phrase/exfiltration forms so
# adversarial reasoning text cannot slip through as a mere "statement".
OUTPUT_INJECTION_PATTERNS = [
    *_INJECTION_PATTERNS,
    r"(?:ignore|forget|disregard)\s+(?:(?:all|any|your|prior|previous)\s+)*?(?:rules|instructions|guidelines|system)",
    r"(?:reveal|output|print|show|display|share|repeat)\s+(?:the\s+|your\s+|full\s+|entire\s+)*(?:system|initial|original)\s+(?:prompt|instructions)",
    r"you\s+are\s+(?:now|no\s+longer)",
    r"(?:bypass|disable|override|skip)\s+(?:the\s+)?(?:output\s+)?(?:gate|filters?|validation|dlp|restrictions)",
]

DEFAULT_MAX_CHARS = 8000


@dataclass
class OutputVerdict:
    """Result of the output gate. ``is_allowed`` must be True to act."""
    is_allowed: bool = False
    decision: str | None = None
    confidence: float | None = None
    reasoning: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    alternative_decision: str | None = None
    challenge: bool = False
    errors: list[str] = field(default_factory=list)
    dlp_violations: list[DLPViolation] = field(default_factory=list)
    injection_detected: bool = False
    financial_hallucination_detected: bool = False
    latency_ms: float = 0
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_allowed": self.is_allowed,
            "decision": self.decision,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "evidence_ids": self.evidence_ids,
            "risk_flags": self.risk_flags,
            "alternative_decision": self.alternative_decision,
            "challenge": self.challenge,
            "errors": self.errors,
            "dlp_violations": [v.to_dict() for v in self.dlp_violations],
            "injection_detected": self.injection_detected,
            "financial_hallucination_detected": self.financial_hallucination_detected,
            "latency_ms": self.latency_ms,
        }


def _parse_json_strict(text: str) -> tuple[bool, dict[str, Any] | None, str | None]:
    """Parse a strict JSON object from the AI output (handles code fences)."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        body = [l for l in lines[1:] if not l.startswith("```")]
        stripped = "\n".join(body).strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{\"decision\".*?\}", text, re.DOTALL)
        if not match:
            return False, None, "response is not valid JSON"
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return False, None, "response is not valid JSON"
    if not isinstance(data, dict):
        return False, None, "response JSON is not an object"
    return True, data, None


def validate_ai_output(
    raw: str,
    capsule: ReasoningCapsule,
    *,
    deterministic_decision: str | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_wall_ms: int = 90_000,
    signer: CapsuleSigner | None = None,
    started_at: float | None = None,
    allowed_decisions: frozenset[str] | None = None,
) -> OutputVerdict:
    """Validate an AI response string against its capsule. Fail-closed."""
    verdict = OutputVerdict(raw_response=raw[:max_chars])
    if started_at is not None:
        verdict.latency_ms = (time.monotonic() - started_at) * 1000

    errors = verdict.errors

    # 1. Integrity of the capsule itself.
    ok_signature = (signer or CapsuleSigner()).verify(capsule)
    if not ok_signature:
        errors.append("capsule_signature_invalid")
    if capsule.is_fresh(datetime.now(timezone.utc)) is not True:
        errors.append("capsule_expired")

    # 2. Size cap.
    if not raw or not raw.strip():
        errors.append("empty_response")
    if len(raw) > max_chars:
        errors.append(f"response_too_large>={max_chars}")

    if errors:
        verdict.is_allowed = False
        return verdict

    # 3. DLP on raw response.
    scanner = DlpScanner(strict=True)
    verdict.dlp_violations = scanner.scan(raw)
    if verdict.dlp_violations:
        errors.append("dlp_blocked")

    # 4. JSON structure.
    parsed_ok, data, parse_error = _parse_json_strict(raw)
    if not parsed_ok:
        errors.append(parse_error or "unparseable")

    if errors:
        verdict.is_allowed = False
        return verdict

    # 5. Financial hallucination: capsule carries NO absolute values.
    for pattern in SAR_PATTERNS:
        if pattern.search(raw):
            verdict.financial_hallucination_detected = True
            errors.append("financial_hallucination_detected")
            break

    # 6. Injection patterns.
    for pattern in OUTPUT_INJECTION_PATTERNS:
        if re.search(pattern, raw, re.IGNORECASE):
            errors.append("prompt_injection_detected")
            verdict.injection_detected = True
            break

    decision = str(data.get("decision", "MANUAL_REVIEW")).upper()
    candidate_set = allowed_decisions or capsule.allowed_decisions()
    if decision not in candidate_set:
        errors.append(f"decision_not_in_candidates:{decision}")

    # 7. Decision enum sanity + confidence range.
    valid_decisions = frozenset({
        "DO_NOTHING", "REORDER", "TRANSFER", "DISCOUNT",
        "PRICE_CHANGE", "RECOVERY_MATCH", "MANUAL_REVIEW",
    })
    if decision not in valid_decisions:
        errors.append(f"decision_invalid:{decision}")

    try:
        confidence = float(data.get("confidence", 0.0))
        if not (0.0 <= confidence <= 1.0):
            errors.append("confidence_out_of_range")
            confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        errors.append("confidence_invalid")
        confidence = 0.0

    # 8. Evidence ids must be capsule signals / opaque refs.
    evidence_ids = data.get("evidence_ids", None)
    if not isinstance(evidence_ids, list):
        errors.append("evidence_ids_not_list")
        evidence_ids = []
    allowed_ev = capsule.allowed_evidence()
    for eid in evidence_ids:
        if not isinstance(eid, str) or eid not in allowed_ev:
            errors.append(f"evidence_id_not_in_capsule:{eid}")

    reasoning = data.get("reasoning", "")
    if not isinstance(reasoning, str) or len(reasoning.strip()) < 5:
        errors.append("reasoning_missing_or_short")

    risk_flags = data.get("risk_flags", [])
    if not isinstance(risk_flags, list):
        errors.append("risk_flags_not_list")
        risk_flags = []

    alt = data.get("alternative_decision")
    challenge = bool(data.get("challenge", False))
    if isinstance(alt, str):
        alt = alt.upper()
        if alt not in valid_decisions:
            errors.append("alternative_decision_invalid")

    if errors:
        verdict.is_allowed = False
        return verdict

    if deterministic_decision and decision != deterministic_decision:
        # A different decision is allowed only if the AI is explicit about
        # challenging the deterministic decision; otherwise reject.
        if not challenge and "challenge" not in str(reasoning).lower():
            errors.append("decision_diverges_without_challenge")
            verdict.is_allowed = False
            return verdict

    verdict.is_allowed = True
    verdict.decision = decision
    verdict.confidence = confidence
    verdict.reasoning = reasoning
    verdict.evidence_ids = evidence_ids
    verdict.risk_flags = risk_flags
    verdict.alternative_decision = alt
    verdict.challenge = challenge
    return verdict
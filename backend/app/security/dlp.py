"""Data Loss Prevention: outbound content scanner.

Applied on both sides of the AI boundary:
  - outbound prompts (built from capsules) before they reach any LLM provider
    or the OpenCode CLI,
  - inbound AI responses before they are trusted by the output gate.

Any match is a hard BLOCK (fail-closed). No silent redaction.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

# Ordered DLP rule set. ``label`` is machine-readable; ``pattern`` matches a
# violation. Rules are read-only policy, not data.
DLP_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"(?<![@\w.])[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b", re.IGNORECASE)),
    ("PHONE_KSA", re.compile(r"(?<![\d])(?:\+?966[\s-]?5\d{8}|05\d{8})(?![\d])")),
    ("JWT", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("API_KEY_OPENAI", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("API_KEY_GENERIC", re.compile(r"\b(?:api[_-]?key|apikey)[\s=:]{1,3}['\"]*[A-Za-z0-9+/=_-]{16,}", re.IGNORECASE)),
    ("BEARER_TOKEN", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}", re.IGNORECASE)),
    ("PRIVATE_KEY", re.compile(r"-----BEGIN\s+(?:RSA\s+|EC\s+|OPENSSH\s+|DSA\s+)?PRIVATE\s+KEY-----")),
    ("DB_URL", re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\\+srv)?|redis|amqp|jdbc)\s*[:/][^\s\"']+", re.IGNORECASE)),
    ("SQL_STATEMENT", re.compile(r"\b(?:SELECT\s+\*?\s+FROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|DROP\s+TABLE|ALTER\s+TABLE)\b", re.IGNORECASE)),
    ("UUID", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)),
    ("SECRET_ASSIGNMENT", re.compile(r"\b(?:password|passwd|secret|token|access[_-]?key|private[_-]?key|client[_-]?secret)\s*[:=]\s*\S+", re.IGNORECASE)),
    ("CREDENTIAL_MASTER_KEY", re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b")),
]


@dataclass
class DLPViolation:
    label: str
    sample: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"label": self.label, "sample": self.sample}


class DlpScanner:
    """Scans text/objects for prohibited data. One instance per boundary call."""

    def __init__(self, rules: Iterable[tuple[str, re.Pattern[str]]] = DLP_RULES, strict: bool = True):
        self._rules = list(rules)
        self.strict = strict

    def scan(self, text: str) -> list[DLPViolation]:
        if not text:
            return []
        violations: list[DLPViolation] = []
        for label, pattern in self._rules:
            match = pattern.search(text)
            if match:
                sample = match.group(0)
                if len(sample) > 40:
                    sample = sample[:18] + "..." + sample[-18:]
                violations.append(DLPViolation(label=label, sample=sample))
        return violations

    def scan_object(self, obj: Any) -> list[DLPViolation]:
        """Recursively scan dicts/lists and aggregate string matches."""
        violations: list[DLPViolation] = []
        if isinstance(obj, dict):
            for key, value in obj.items():
                violations.extend(self.scan_object(key))
                violations.extend(self.scan_object(value))
        elif isinstance(obj, (list, tuple)):
            for value in obj:
                violations.extend(self.scan_object(value))
        elif isinstance(obj, str):
            violations.extend(self.scan(obj))
        return violations

    def assert_clean(self, text: str, *, context: str = "generic") -> None:
        violations = self.scan(text)
        if violations:
            raise DLPViolationError(context=context, violations=violations)

    def assert_clean_object(self, obj: Any, *, context: str = "generic") -> None:
        violations = self.scan_object(obj)
        if violations:
            raise DLPViolationError(context=context, violations=violations)


class DLPViolationError(Exception):
    """Raised when outbound or inbound data matches a DLP rule."""

    def __init__(self, context: str, violations: list[DLPViolation]):
        self.context = context
        self.violations = violations
        labels = ", ".join(sorted({v.label for v in violations}))
        super().__init__(f"DLP blocked ({context}): {labels}")
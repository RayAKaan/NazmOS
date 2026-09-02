"""AI policy: kill switch, capability gating, circuit breaker, budget guard.

Policy checks are the FIRST thing any AI entry point evaluates. When disabled,
AI is never consulted; the deterministic engine's decision is preserved.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

logger = logging.getLogger(__name__)

# Registry of AI capabilities this process can run. Each maps to a purpose the
# request must declare. Unknown capabilities are denied by default.
AI_CAPABILITIES: dict[str, str] = {
    "counterfactual_audit": "resolve ambiguity in inventory decisions",
    "challenge": "challenge the deterministic decision",
    "opencode_brain": "independent reasoning on a decision capsule",
    "chat": "executive copilot answering about the merchant's own business",
}

AI_CAPABILITY_FLAGS: dict[str, Callable[[object], bool]] = {}


def _enabled(attr: str) -> Callable[[object], bool]:
    def check(settings: object) -> bool:
        value = getattr(settings, attr, True)
        return bool(value)
    return check


AI_CAPABILITY_FLAGS["opencode_brain"] = _enabled("AI_ENABLED")
AI_CAPABILITY_FLAGS["counterfactual_audit"] = _enabled("AI_ENABLED")
AI_CAPABILITY_FLAGS["challenge"] = _enabled("AI_ENABLED")
AI_CAPABILITY_FLAGS["chat"] = _enabled("CHAT_ENABLED")


class AiPolicy:
    """Global + per-capability kill switch."""

    def __init__(self, settings: object | None = None):
        self.settings = settings

    def enabled(self, capability: str) -> bool:
        if capability not in AI_CAPABILITIES:
            return False
        if self.settings is None:
            return True
        check = AI_CAPABILITY_FLAGS.get(capability)
        if check is not None and not check(self.settings):
            return False
        return bool(getattr(self.settings, "AI_ENABLED", True))

    def allow_request(self, capability: str, purpose: str) -> tuple[bool, str]:
        if not self.enabled(capability):
            return False, f"AI capability '{capability}' is disabled"
        expected = AI_CAPABILITIES.get(capability)
        if expected and purpose not in expected and purpose != "_internal":
            return False, f"purpose '{purpose}' not permitted for capability '{capability}'"
        return True, ""


class CircuitBreaker:
    """Simple fail-open-when-closed-free circuit breaker for LLM transports."""

    def __init__(self, failure_threshold: int = 5, recovery_seconds: float = 60.0):
        self.failure_threshold = max(1, failure_threshold)
        self.recovery_seconds = max(1.0, recovery_seconds)
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self.recovery_seconds:
            return False
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = time.monotonic()
            logger.warning("ai_circuit_open", extra={"failures": self._failures})


@dataclass
class AiBudgetGuard:
    """Budget wrapper around the existing global AI budget (ai_budget.py)."""
    can_call: Callable[[], bool] = lambda: True  # noqa: E731
    record: Callable[[bool, float], None] = lambda *_: None  # noqa: E731


def enabled_now(settings: object | None = None) -> bool:
    """Quick global check used by entry points that lack capability context."""
    return getattr(settings, "AI_ENABLED", True) if settings is not None else True


def audit_event(
    event_type: str,
    *,
    actor: str | None = None,
    detail: dict | None = None,
) -> None:
    """Sync security log hook (structured, redacted).

    Durable persistence into the ``security_events`` table is performed by
    app.services.security_audit_service.record_security_event() at the async AI
    entry points; this hook keeps a synchronous, process-local trace for callers
    that cannot await.
    """
    logger.info(
        "security_event",
        extra={
            "event_type": event_type,
            "actor": actor,
            "detail": detail or {},
            "ts": datetime.now(timezone.utc).isoformat(),
        },
    )
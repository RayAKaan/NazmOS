"""Phase 5 AI budget and usage accounting.

In-memory per-process accounting is intentional for pilot mode; durable billing
should be introduced only when a billing provider is selected.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from threading import Lock

@dataclass
class AIBudget:
    daily_calls: int = 25
    per_audit_calls: int = 10
    calls_today: int = 0
    calls_this_audit: int = 0
    failures: int = 0
    total_latency_ms: float = 0.0
    total_tokens: int = 0
    _day: date = field(default_factory=date.today)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def _roll(self):
        if self._day != date.today():
            self.calls_today = self.failures = 0
            self.total_latency_ms = self.total_tokens = 0
            self._day = date.today()

    def begin_audit(self):
        with self._lock:
            self._roll(); self.calls_this_audit = 0

    def can_call(self) -> bool:
        with self._lock:
            self._roll()
            return self.calls_today < self.daily_calls and self.calls_this_audit < self.per_audit_calls

    def record(self, *, success: bool, latency_ms: float = 0, tokens: int = 0):
        with self._lock:
            self._roll(); self.calls_today += 1; self.calls_this_audit += 1
            self.total_latency_ms += max(0, latency_ms); self.total_tokens += max(0, tokens)
            if not success: self.failures += 1

    def snapshot(self) -> dict:
        with self._lock:
            self._roll()
            return {"daily_calls": self.daily_calls, "per_audit_calls": self.per_audit_calls,
                    "calls_today": self.calls_today, "calls_this_audit": self.calls_this_audit,
                    "failures": self.failures, "total_latency_ms": round(self.total_latency_ms, 2),
                    "total_tokens": self.total_tokens}

GLOBAL_AI_BUDGET = AIBudget()

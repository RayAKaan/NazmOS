"""Safe LLM transport used by the live Intelligence/Money Audit reasoning path.

The transport enforces outbound and inbound DLP checks. Model output remains
untrusted until the caller validates its structured contract.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from app.security.ai_policy import CircuitBreaker
from app.security.dlp import DLP_RULES, DlpScanner, DLPViolationError

logger = logging.getLogger("ai_adapter")


class AITransportError(Exception):
    """Transport-level failure (timeout, unavailable, DLP block, HTTP error)."""


def _guard_outbound(system_prompt: str, user_prompt: str) -> None:
    scanner = DlpScanner(rules=list(DLP_RULES), strict=True)
    scanner.assert_clean(system_prompt, context="outbound_system")
    scanner.assert_clean(user_prompt, context="outbound_user")


class LLMTransport:
    """Wraps an existing async LLM callable (e.g. LLMOrchestrator chat_completion)."""

    def __init__(
        self,
        llm_caller: Callable[[str, str], Awaitable[str | None]],
        *,
        timeout_seconds: float = 45,
        breaker: CircuitBreaker | None = None,
    ):
        self._caller = llm_caller
        self._timeout = timeout_seconds
        self._breaker = breaker or CircuitBreaker()

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        if self._breaker.is_open:
            raise AITransportError("circuit_open")
        _guard_outbound(system_prompt, user_prompt)
        try:
            response = await asyncio.wait_for(
                self._caller(system_prompt, user_prompt),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError as exc:
            self._breaker.record_failure()
            raise AITransportError("llm_timeout") from exc
        except Exception as exc:
            self._breaker.record_failure()
            raise AITransportError(f"llm_call_failed:{type(exc).__name__}") from exc
        if response is None or not response.strip():
            self._breaker.record_failure()
            raise AITransportError("llm_empty_response")
        try:
            DlpScanner(rules=list(DLP_RULES), strict=True).assert_clean(
                response, context="inbound_response"
            )
        except DLPViolationError as exc:
            self._breaker.record_failure()
            raise AITransportError(f"dlp_inbound:{exc}") from exc
        self._breaker.record_success()
        return response



"""Jev (TypeSafe System One) adapter -- a NON-AUTHORITATIVE AI provider.

Jev is exposed to NazmOS as a simple HTTPS question/answer service:

    POST {base_url}/v1/systemone        Authorization: Bearer {api_key}
    {"model": "jev-1.13.0",
     "state": { ...capsule.for_prompt() view... },
     "questions": {"Q1": "..."}}

The response carries answers keyed by question id; each answer may carry one of
the TypeSafe question types (choice / score / noul) plus an explanation.

Security constraints enforced here:
  * Jev is never authoritative -- the deterministic NazmOS decision always
    wins. This adapter exposes ``consult()`` which returns an advisory
    ``JevReply``; the canonical gateway decides how (or whether) to use it.
  * Jev only ever receives the DLP-clean ``capsule.for_prompt()`` view (opaque
    refs + banded signals). Never SKUs, ids, names, exact SAR, credentials.
  * On any transport/parse/validation failure the adapter fails closed: the
    caller supplies a deterministic decision and gets an advisory reply that
    explicitly carries the deterministic decision, guaranteeing the
    deterministic path is never disturbed.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import JevSettings, get_settings
from app.security.capsule import ReasoningCapsule

logger = logging.getLogger("ai_providers.jev")

RETRYABLE_STATUS = {429, 500, 502, 503, 529}
NUM_RETRIES = 2
BACKOFF_SECONDS = 1.0


@dataclass
class JevReply:
    """Advisory (never authoritative) reply from Jev.

    decision_basis is ALWAYS the deterministic decision supplied by the caller
    -- this is the invariant that keeps Jev non-authoritative.
    """

    source: str = "jev"  # "jev" | "fallback"
    decision_basis: str = "DO_NOTHING"
    suggested_decision: str | None = None
    confidence: float = 0.0
    reasoning: str = ""
    challenge: bool = False
    latency_ms: float = 0
    errors: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class JevError(Exception):
    """Base error for Jev transport/parse failures."""


class JevUnavailable(JevError):
    """Jev is not configured (birthday off) -- treated as a no-op, not a fault."""


class JevClient:
    """Thin httpx client over the TypeSafe System One endpoint.

    Direct httpx; no SDK dependency. Matches the repo convention of raw httpx
    for all external AI traffic (see llm_orchestrator.py).
    """

    def __init__(
        self,
        *,
        settings: JevSettings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    @property
    def settings(self) -> JevSettings:
        return self._settings or get_settings().jev

    @property
    def enabled(self) -> bool:
        return self.settings.configured

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        s = self.settings
        client_kwargs: dict[str, Any] = {
            "timeout": httpx.Timeout(s.timeout_seconds),
        }
        if self._transport is not None:  # tests inject a stub transport
            client_kwargs["transport"] = self._transport
        headers = {
            "Authorization": f"Bearer {s.api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        for attempt in range(NUM_RETRIES + 1):
            try:
                async with httpx.AsyncClient(**client_kwargs) as client:
                    resp = await client.post(s.base_url, json=payload, headers=headers)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in RETRYABLE_STATUS:
                    last_error = JevError(
                        f"httpx {resp.status_code} retryable; will backoff and retry"
                    )
                    if attempt < NUM_RETRIES:
                        await asyncio_sleep(BACKOFF_SECONDS * (attempt + 1))
                        continue
                    break
                raise JevError(f"Jev returned HTTP {resp.status_code}")
            except httpx.TimeoutException as exc:
                last_error = JevError(f"Jev timeout: {exc}")
                if attempt < NUM_RETRIES:
                    await asyncio_sleep(BACKOFF_SECONDS * (attempt + 1))
                    continue
                break
            except httpx.TransportError as exc:
                last_error = JevError(f"Jev transport error: {exc}")
                if attempt < NUM_RETRIES:
                    await asyncio_sleep(BACKOFF_SECONDS * (attempt + 1))
                    continue
                break
        raise JevError(f"Jev request failed: {last_error}") if last_error else JevError("Jev request failed")


async def asyncio_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _extract_answer(reply: dict[str, Any], question_id: str) -> dict[str, Any]:
    """Dig Jev's answer object out of the common response shapes."""
    # Shape A: {"answers": {"Q1": {...}}, ...}
    answers = reply.get("answers")
    if isinstance(answers, dict):
        ans = answers.get(question_id)
        if isinstance(ans, dict):
            return ans
    # Shape B: {"responses": [{"question_id": "Q1", ...}], ...}
    for bucket in ("responses", "results", "items"):
        seq = reply.get(bucket)
        if isinstance(seq, list):
            for entry in seq:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("question_id", entry.get("id", ""))) == question_id:
                    return entry
    # Shape C: the whole reply is the single answer
    return reply


VALID_SUGGESTIONS = frozenset({
    "DO_NOTHING",
    "REORDER",
    "TRANSFER",
    "DISCOUNT",
    "PRICE_CHANGE",
    "RECOVERY_MATCH",
    "MANUAL_REVIEW",
})


def _score_to_confidence(raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, value))


async def consult(
    *,
    question: str,
    capsule: ReasoningCapsule,
    deterministic_decision: str,
    client: JevClient | None = None,
    allowed_suggestions: frozenset[str] | None = None,
) -> JevReply:
    """Advisory Jev consultation for one question.

    Never authoritative. ``deterministic_decision`` is preserved on the reply
    unconditionally and used as the decision_basis on any failure.

    ``allowed_suggestions`` is the vocabulary this call is valid in. Default
    (None) keeps the adapter fail-closed: suggestions outside the registered
    action vocabulary are discarded and the reply is ``source=="fallback"``.
    When a surface passes its own contract (e.g. the canonical controller's
    rank buckets / root-cause taxonomy), the adapter surfaces the suggestion
    verbatim so that surface's output gate -- the authoritative contract
    owner -- can accept, reject, and flag it (adapter no longer owns the
    contract in that case).

    Type-level invariant: ``capsule`` MUST be a signed ReasoningCapsule. A raw
    evidence dict is a TypeError -- raw merchant data never reaches Jev.
    """
    if not isinstance(capsule, ReasoningCapsule):
        raise TypeError(
            "consult() requires a signed ReasoningCapsule. Raw evidence dicts "
            "are never sent to the AI (Phase A isolation core)."
        )

    client = client or JevClient()
    if not client.enabled:
        return JevReply(
            source="fallback",
            decision_basis=deterministic_decision,
            reasoning="Jev disabled or not configured; deterministic decision retained.",
            errors=["jev_not_configured"],
        )

    try:
        state = capsule.for_prompt()
    except AttributeError:
        state = {}

    if not capsule.is_fresh():
        return JevReply(
            source="fallback",
            decision_basis=deterministic_decision,
            reasoning="Capsule expired before Jev consultation.",
            errors=["capsule_expired"],
        )

    payload = {
        "model": client.settings.model,
        "state": state,
        "questions": {"Q1": question},
    }

    start = time.monotonic()
    try:
        reply = await client._post(payload)
    except (JevUnavailable, JevError) as exc:
        logger.warning("jev_consult_failed", extra={"reason": str(exc)})
        return JevReply(
            source="fallback",
            decision_basis=deterministic_decision,
            reasoning=f"Jev consultation failed ({exc}); deterministic decision retained.",
            errors=[str(exc)],
        )

    latency = (time.monotonic() - start) * 1000

    # Non-authoritative normalization: Jev's suggestion is cast to a suggestion,
    # never a decision, and must be a registered action to be usable at all.
    answer = _extract_answer(reply, "Q1")
    suggested = answer.get("choice") or answer.get("decision") or answer.get("value")
    suggested = str(suggested).upper() if suggested else None

    challenge = bool(answer.get("challenge", False))
    reasoning = str(answer.get("explanation") or answer.get("reasoning") or "").strip()
    confidence = _score_to_confidence(
        answer.get("score", answer.get("confidence", answer.get("probability", 0.5)))
    )

    if suggested is not None and suggested not in (allowed_suggestions or VALID_SUGGESTIONS):
        logger.warning(
            "jev_out_of_contract_suggestion",
            extra={
                "suggestion": suggested,
                "latency_ms": latency,
                "declared_vocabulary": allowed_suggestions is not None,
            },
        )
        if allowed_suggestions is None:
            return JevReply(
                source="fallback",
                decision_basis=deterministic_decision,
                reasoning=f"Jev returned out-of-contract suggestion {suggested!r}; deterministic decision retained.",
                confidence=confidence,
                challenge=challenge,
                latency_ms=latency,
                errors=[f"invalid_suggestion:{suggested}"],
                raw=answer,
            )
        # A surface declared its own vocabulary: the suggestion is surfaced
        # verbatim so that surface's output gate (e.g. the canonical
        # controller) owns contract enforcement and can discard/flag it.

    return JevReply(
        source="jev",
        decision_basis=deterministic_decision,
        suggested_decision=suggested,
        confidence=confidence,
        reasoning=reasoning or "Jev advisory; deterministic decision retained.",
        challenge=challenge,
        latency_ms=latency,
        raw=answer,
    )
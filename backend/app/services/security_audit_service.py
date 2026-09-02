"""Durable security event + AI reasoning request audit (Phase A migration ff05).

All AI entry points record a security event / reasoning request here so the
``security_events`` and ``ai_reasoning_requests`` tables become the forensic
trail for the isolation core. Writes are best-effort: any persistence failure
is logged and returned as ``False`` so audit friction can never break a
decision flow.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


def _none_aware_iso(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


# Only these bounded, non-sensitive keys may be persisted in audit ``detail``.
# Free-form text (reasoning, prompts, notes) is never allowed into the table.
_ALLOWED_DETAIL_KEYS = frozenset(
    {
        "source",
        "decision",
        "confidence",
        "reason",
        "latency_ms",
        "capability",
        "is_valid",
        "status",
        "error",
        "request_id",
        "actor",
    }
)


def _scrub_detail(detail: dict[str, Any] | None) -> dict[str, Any] | None:
    """Keep only allowlisted, bounded, primitive values from audit detail.

    Prompt text, reasoning strings and merchant data keys are dropped so the
    forensic table never stores anything that could leak business data.
    """
    if not isinstance(detail, dict):
        return None
    out: dict[str, Any] = {}
    for k, v in detail.items():
        if k not in _ALLOWED_DETAIL_KEYS or v is None:
            continue
        if not isinstance(v, (str, int, float, bool, datetime, date)):
            continue
        if isinstance(v, str):
            v = v[:200]
        out[str(k)] = _none_aware_iso(v)
    return out or None


async def record_security_event(
    *,
    event_type: str,
    actor: str | None = None,
    business_id: str | UUID | None = None,
    capsule_id: str | None = None,
    request_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> bool:
    """Persist a security event into ``security_events`` (best-effort)."""
    try:
        from app.database.connection import async_session_scope
        from app.database.models import SecurityEvent

        async with async_session_scope() as session:
            session.add(
                SecurityEvent(
                    business_id=str(business_id) if business_id else None,
                    event_type=str(event_type)[:40],
                    actor=str(actor)[:80] if actor else None,
                    capsule_id=str(capsule_id)[:64] if capsule_id else None,
                    request_id=str(request_id)[:64] if request_id else None,
                    detail=_scrub_detail(detail),
                )
            )
            await session.commit()
        return True
    except Exception:
        logger.exception("security_event_persist_failed", extra={"event_type": event_type})
        return False


async def record_ai_reasoning_request(
    *,
    capsule_id: str,
    request_id: str,
    nonce: str,
    capsule_hash: str,
    capability: str,
    purpose: str | None,
    issued_at: datetime,
    expires_at: datetime,
    business_id: str | UUID | None = None,
    status: str = "requested",
    decision: str | None = None,
    error: str | None = None,
) -> bool:
    """Persist an AI reasoning request fingerprint (no capsule payload!).

    Only bookkeeping is stored: never the prompt, capsule body, or any merchant
    data. ``error`` is a bounded machine tag such as ``AITransportError``.
    """
    try:
        from app.database.connection import async_session_scope
        from app.database.models import AIReasoningRequest

        async with async_session_scope() as session:
            session.add(
                AIReasoningRequest(
                    business_id=str(business_id) if business_id else None,
                    capsule_id=str(capsule_id)[:64],
                    request_id=str(request_id)[:64],
                    nonce=str(nonce)[:64],
                    capsule_hash=str(capsule_hash)[:64],
                    capability=str(capability)[:40],
                    purpose=str(purpose)[:120] if purpose else None,
                    issued_at=issued_at if issued_at.tzinfo else issued_at.replace(tzinfo=timezone.utc),
                    expires_at=expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc),
                    status=str(status)[:20],
                    decision=str(decision)[:30] if decision else None,
                    error=str(error)[:200] if error else None,
                )
            )
            await session.commit()
        return True
    except Exception:
        logger.exception("ai_reasoning_persist_failed", extra={"capsule_id": capsule_id})
        return False
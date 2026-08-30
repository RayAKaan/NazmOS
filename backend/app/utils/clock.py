"""Virtual business clock (Phase 13, §Part 2).

A minimal, non-invasive clock abstraction so synthetic merchant scenarios can simulate
historical business time (Day 1 → Day 14, 30-day, 90-day histories) instantly — WITHOUT
`sleep`, Celery Beat, or real calendar waiting.

Production semantics are unchanged: `utcnow()` returns the real current time unless a test
explicitly sets a virtual "now" via `set_virtual_now`. The override is a contextvar, so it is
isolated per async task / test and never leaks between tests.

The deterministic evaluation functions that consume "now" (recency, freshness, regime)
already accept an explicit `now` parameter where it matters; this module provides the shared
source for anything that reads wall-clock time in tests.
"""
from __future__ import annotations

import contextvars
from datetime import datetime, timezone
from typing import Optional

_virtual_now: contextvars.ContextVar[Optional[datetime]] = contextvars.ContextVar(
    "nazmos_virtual_now", default=None
)


def utcnow() -> datetime:
    """Return the current UTC time — real, unless a virtual clock is set (tests only)."""
    virtual = _virtual_now.get()
    if virtual is not None:
        return virtual
    return datetime.now(timezone.utc)


def set_virtual_now(dt: datetime | None) -> None:
    """Set or clear the virtual clock (test-only). Contextvar-scoped to the current task."""
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    _virtual_now.set(dt)


def advance_days(days: int) -> datetime:
    """Advance the virtual clock by N days and return the new 'now' (test helper)."""
    from datetime import timedelta
    new_now = utcnow() + timedelta(days=days)
    set_virtual_now(new_now)
    return new_now


def now() -> datetime:
    """Canonical application/business UTC time."""
    return utcnow()

def today():
    return utcnow().date()

def reset_virtual_now() -> None:
    set_virtual_now(None)

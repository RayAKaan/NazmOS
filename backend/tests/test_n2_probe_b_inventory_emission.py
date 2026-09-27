"""N2 probe B — deterministic, single-run, full-args emission capture.

Uses the REAL committed fixture generator (`tests.test_analytics_health_score.sqlite_db`)
and REAL committed seed (`_seed`) via pytest's REAL fixture machinery. Attaches a
`before_cursor_execute` listener on the REAL sqlite sync engine and captures the
FULL (json.dump, no truncation) inventory INSERT bound parameters into
`%TEMP%/opencode/n2_probeB_inventory_events.json`.

Temporary probe — deleted after review.
"""

import json
import os

import pytest
from sqlalchemy import event

from tests.test_analytics_health_score import _seed as real_seed
from tests.test_analytics_health_score import sqlite_db as real_sqlite_db

_OUT = os.path.join(os.environ.get("TEMP", "/tmp"), "opencode", "n2_probeB_inventory_events.json")


def _summarize_row(r):
    if not isinstance(r, dict):
        return {"type": type(r).__name__}
    return {
        "id": str(r.get("id", ""))[:8],
        "business_id": str(r.get("business_id", ""))[:8],
        "item_id": str(r.get("item_id", ""))[:8],
        "location_id": r.get("location_id"),
        "current_stock": r.get("current_stock"),
    }


def _params_to_rows(params):
    if isinstance(params, list) and params and isinstance(params[0], dict):
        return [_summarize_row(r) for r in params]
    if isinstance(params, (list, tuple)):
        return [{"__seqlen": len(params), "first": _summarize_row(params[0]) if params else None}]
    return [_summarize_row(params)]


@pytest.mark.asyncio
async def test_n2_probe_b_inventory_emission(real_sqlite_db):
    events = []

    def _hook(conn, cursor, statement, parameters, context, executemany):
        low = statement.lower()
        if "insert into inventory" not in low:
            return
        events.append(
            {
                "executemany": bool(executemany),
                "rows": _params_to_rows(parameters),
            }
        )

    SessionLocal, sync_engine = real_sqlite_db
    event.listen(sync_engine, "before_cursor_execute", _hook)
    try:
        async with SessionLocal() as db:
            await real_seed(db)
    finally:
        event.remove(sync_engine, "before_cursor_execute", _hook)

    os.makedirs(os.path.dirname(_OUT), exist_ok=True)
    with open(_OUT, "w", encoding="utf-8") as fh:
        json.dump({"events": events}, fh, indent=1)

    assert events, "no inventory INSERT emission captured"
    print(f"n2_probeB_captured={_OUT} events={len(events)}")
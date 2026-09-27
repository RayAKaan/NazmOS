"""N2D probe — capture the REAL inventory INSERT emission, untruncated.

Drives the REAL committed fixture generator (`tests.test_analytics_health_score.sqlite_db`)
via pytest's REAL fixture machinery and the REAL committed seed helper (`_seed`),
destructuring the `(SessionLocal, sync_engine)` tuple exactly like the committed
health-score tests. A `before_cursor_execute` listener on the REAL sqlite sync
engine captures EVERY statement that really inserts into `inventory`. Full bound
rows (summarized — no full UUIDs) go to a temp capture JSON file. No
re-implementation of the seed or the fixture. Temporary probe — deleted after
capture.
"""

import json
import os

import pytest
from sqlalchemy import event

from tests.test_analytics_health_score import _seed as real_seed
from tests.test_analytics_health_score import sqlite_db as real_sqlite_db

_CAPTURE = os.path.join(
    os.environ.get("TEMP", "/tmp"), "opencode", "n2d_probe_inventory_capture.json"
)


def _rows_summary(parameters):
    """Minimal per-row summary; do NOT leak full UUIDs."""
    rows = list(parameters) if isinstance(parameters, (list, tuple)) else [parameters]
    out = []
    for r in rows:
        if isinstance(r, dict):
            out.append(
                {
                    "business": str(r.get("business_id", ""))[:8],
                    "item": str(r.get("item_id", ""))[:8],
                    "loc": r.get("location_id"),
                }
            )
        else:
            out.append(f"nondict:{type(r).__name__}")
    return out


@pytest.mark.asyncio
async def test_n2d_capture_real_inventory_emission(real_sqlite_db):
    rows_found = []

    def _hook(conn, cursor, statement, parameters, context, executemany):
        low = statement.lower()
        if "insert into inventory" not in low:
            return
        rows_found.append(
            {
                "executemany": bool(executemany),
                "nparams_total": len(parameters)
                if isinstance(parameters, (list, tuple))
                else "scalar",
                "rows": _rows_summary(parameters),
                "statement_prefix": statement[:120],
            }
        )

    SessionLocal, sync_engine = real_sqlite_db
    event.listen(sync_engine, "before_cursor_execute", _hook)
    try:
        async with SessionLocal() as db:
            await real_seed(db)
    finally:
        event.remove(sync_engine, "before_cursor_execute", _hook)

    os.makedirs(os.path.dirname(_CAPTURE), exist_ok=True)
    with open(_CAPTURE, "w", encoding="utf-8") as fh:
        json.dump({"events": rows_found}, fh, indent=1)

    print(f"PROBE captured={_CAPTURE} n_events={len(rows_found)}")
    assert rows_found, "no inventory INSERT emission captured"
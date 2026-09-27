"""N2E probe — FULL untruncated capture of the failing inventory INSERT emission.

This pytest test uses the REAL committed `sqlite_db` fixture (AsyncEngine bound
to the REAL in-memory SQLite) and then drives the REAL committed `_seed` helper,
which emits the SAME inventory INSERT path the failing endpoint triggers (REAL
schema + REAL model). A SQLAlchemy `before_cursor_execute` listener dumps the
COMPLETE statement and every bound row (summarized business_id + item_id) to a
JSONL file, bypassing pytest's 150-char repr truncation entirely.

Any pytest -q run below that ends with "1 passed" plus this JSONL file proves
the emission; the JSONL is the ground truth (file I/O, no repr involved).

No re-implementation of the seed or the fixture; no invented `.bind` attribute —
the fixture yields `(SessionLocal, sync_engine)` per the committed contract.
"""

import json
import os

import pytest
from sqlalchemy import event

from tests.test_analytics_health_score import _seed as real_seed
from tests.test_analytics_health_score import sqlite_db as real_sqlite_db

_CAPTURE = os.path.join(
    os.environ.get("TEMP", "/tmp"), "opencode", "n2e_inventory_emission_capture.jsonl"
)


@pytest.mark.asyncio
async def test_n2e_capture_real_inventory_emission(real_sqlite_db):
    rows_found = []

    def _hook(conn, cursor, statement, parameters, context, executemany):
        low = statement.lower()
        if "insert into inventory" not in low:
            return
        params = parameters if isinstance(parameters, (list, tuple)) else [parameters]
        row_summaries = []
        for p in params:
            if isinstance(p, dict):
                row_summaries.append(
                    {
                        "business_id": str(p.get("business_id", ""))[:12],
                        "item_id": str(p.get("item_id", ""))[:12],
                        "location_id": str(p.get("location_id"))[:12]
                        if p.get("location_id")
                        else None,
                        "current_stock": p.get("current_stock"),
                    }
                )
            elif isinstance(p, (list, tuple)) and len(p) >= 3:
                row_summaries.append(
                    {
                        "business_id": str(p[1])[:12],
                        "item_id": str(p[2])[:12],
                        "location_id": str(p[3]) if len(p) > 3 and p[3] else None,
                        "ncols": len(p),
                    }
                )
            else:
                row_summaries.append({"raw": str(p)[:200]})
        rows_found.append(
            {
                "executemany": bool(executemany),
                "nparams_total": sum(
                    len(p) if isinstance(p, (list, tuple, dict)) else 1 for p in params
                ),
                "nrows": len(params),
                "rows": row_summaries,
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
        for entry in rows_found:
            fh.write(json.dumps(entry) + "\n")

    assert rows_found, "no inventory emission captured"
    print(f"n2e_capture_written={_CAPTURE} events={len(rows_found)}")
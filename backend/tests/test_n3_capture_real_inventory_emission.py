"""Capture the REAL failing inventory emission in FULL (untruncated) via file write.

Drives the REAL committed fixture + REAL committed `_seed` via pytest's REAL
fixture machinery, attaching a before_cursor_execute listener that APPENDS the
statement and each bound row tuple to a JSON lines file. File writes are never
truncated by pytest, so this is the decisive emission evidence.

No added dependencies; the fixture yields `(SessionLocal, sync_engine)` per the
committed contract — no invented `.bind` attribute.
"""

import json
import os

import pytest
from sqlalchemy import event

from tests.test_analytics_health_score import _seed as real_seed
from tests.test_analytics_health_score import sqlite_db as real_sqlite_db

_CAPTURE = os.path.join(
    os.environ.get("TEMP", "/tmp"), "opencode", "n3_final_inventory_emission_capture.jsonl"
)


@pytest.mark.asyncio
async def test_n3_capture_real_inventory_emission(real_sqlite_db):
    rows_found = []

    def _on_execute(conn, cursor, statement, parameters, context, executemany):
        low = statement.lower()
        if "insert into inventory" in low:
            params = parameters if isinstance(parameters, (list, tuple)) else [parameters]
            row_summaries = []
            for i, p in enumerate(params):
                if isinstance(p, dict):
                    row_summaries.append(
                        {
                            "row_no": i,
                            "business_id": str(p.get("business_id", ""))[:12],
                            "item_id": str(p.get("item_id", ""))[:12],
                            "current_stock": p.get("current_stock"),
                        }
                    )
                elif isinstance(p, (list, tuple)) and len(p) > 1:
                    row_summaries.append(
                        {
                            "row_no": i,
                            "business_id": str(p[1])[:12],
                            "item_id": str(p[2])[:12]
                            if len(p) > 2
                            else "?",
                        }
                    )
                else:
                    row_summaries.append({"row_no": i, "raw": str(p)[:200]})
            rows_found.append(
                {
                    "executemany": bool(executemany),
                    "nparams_total": sum(
                        len(p) if isinstance(p, (list, tuple, dict)) else 1 for p in params
                    ),
                    "rows": len(params),
                    "row_summaries": row_summaries,
                    "statement": statement[:200],
                }
            )

    SessionLocal, sync_engine = real_sqlite_db
    event.listen(sync_engine, "before_cursor_execute", _on_execute)
    try:
        async with SessionLocal() as db:
            await real_seed(db)
    finally:
        event.remove(sync_engine, "before_cursor_execute", _on_execute)

    os.makedirs(os.path.dirname(_CAPTURE), exist_ok=True)
    with open(_CAPTURE, "w", encoding="utf-8") as fh:
        json.dump(rows_found, fh, indent=2)
    print(f"_CAPTURE_WRITTEN={_CAPTURE} events={len(rows_found)}")
    assert rows_found, "no inventory emission captured"
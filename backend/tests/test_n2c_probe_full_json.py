"""N2 probe C — pytest-style, reads the REAL fixture + REAL _seed, dumps full
inventory INSERT bound rows to a JSON file (bypasses pytest/console truncation).

Temporary; deleted after capture.
"""

import asyncio
import json
import os
import tempfile

from sqlalchemy import event

from tests.test_analytics_health_score import _seed as real_seed
# This probe uses the sessionmaker contract (sqlite_db.bind.sync_engine,
# sqlite_db()), which test_analytics_health_score's tuple-returning fixture
# does not provide; test_analytics_item_detail yields the bare sessionmaker.
from tests.test_analytics_item_detail import sqlite_db  # noqa: F401  (fixture)

_CAPTURE = os.path.join(tempfile.gettempdir(), "n2c_inventory_emission_full.json")


def _row_tuple(row):
    if not isinstance(row, dict):
        return row
    return {
        "id": str(row.get("id", ""))[:8],
        "business_id": str(row.get("business_id", ""))[:8],
        "item_id": str(row.get("item_id", ""))[:8],
        "location_id": str(row.get("location_id")),
        "current_stock": row.get("current_stock"),
    }


async def test_n2c_probe_inventory_emission_full(sqlite_db):
    events = []

    def _listener(conn, cursor, statement, parameters, context, executemany):
        low = statement.lower()
        if "insert into inventory" in low:
            rows = parameters if isinstance(parameters, (list, tuple)) else [parameters]
            events.append(
                {
                    "executemany": executemany,
                    "stmt": statement,
                    "n_rows_captured": len(rows),
                    "rows": [_row_tuple(r) for r in rows[:6]],
                }
            )

    # SQLAlchemy 2.x no longer exposes ``sessionmaker.bind``; the engine the
    # sessionmaker was bound to lives in its constructor kwargs.
    sync_engine = sqlite_db.kw["bind"].sync_engine
    event.listen(sync_engine, "before_cursor_execute", _listener)
    try:
        async with sqlite_db() as db:
            await real_seed(db)
    finally:
        event.remove(sync_engine, "before_cursor_execute", _listener)

    with open(_CAPTURE, "w", encoding="utf-8") as fh:
        json.dump(events, fh, indent=1, default=str)
    print(f"N2C capture_written={_CAPTURE} events={len(events)}")

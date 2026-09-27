"""N2-B probe — capture FULL untruncated inventory INSERT bound rows.

Uses the REAL committed `sqlite_db` fixture (via pytest fixture chain) and the
REAL committed `_seed`. Writes every inventory INSERT statement + FULL bound
row tuples (JSON, untruncated) to a capture file, bypassing pytest's
150-char-per-line output truncation.

Temporary — deleted after capture.
"""

import asyncio
import json
import os
import tempfile
import uuid

import pytest
from sqlalchemy import event

from tests.test_analytics_health_score import _seed as real_seed


_CAPTURE = os.path.join(tempfile.gettempdir(), "n2b_inventory_emission_capture.json")


def _full_rows(parameters):
    if isinstance(parameters, dict):
        return {
            "id": str(parameters.get("id", "")),
            "business_id": str(parameters.get("business_id", "")),
            "item_id": str(parameters.get("item_id", "")),
            "location_id": str(parameters.get("location_id", ""))
            if parameters.get("location_id")
            else None,
            "current_stock": parameters.get("current_stock"),
            "nkeys": len(parameters),
            "keys": sorted(parameters.keys()),
        }
    if isinstance(parameters, (list, tuple)) and parameters and isinstance(
        parameters[0], dict
    ):
        return [_full_rows(r) for r in parameters]
    return {"nondict": type(parameters).__name__, "len": len(parameters) if isinstance(parameters, (list, tuple)) else "scalar"}


async def main():
    events = []

    def _on_exec(conn, cursor, statement, parameters, context, executemany):
        low = statement.lower()
        if "insert into inventory" in low or "insert into `inventory`" in low:
            events.append(
                {
                    "executemany": bool(executemany),
                    "full": _full_rows(parameters),
                    "stmt": statement,
                }
            )

    gen = sqlite_db_gen_fixture()
    events_holder = {"events": events, "listener": _on_exec}
    try:
        SessionLocal, sync_engine = await anext(gen)
    except StopAsyncIteration:
        print("N2BPROBE fixture_error=no_value")
        return

    event.listen(sync_engine, "before_cursor_execute", _on_exec)

    try:
        async with SessionLocal() as db:
            business_id = await real_seed(db)
    except Exception as exc:
        print(f"N2BPROBE seed_error={type(exc).__name__}: {str(exc)[:200]}")
    finally:
        event.remove(sync_engine, "before_cursor_execute", _on_exec)
        await gen.aclose()

    with open(_CAPTURE, "w", encoding="utf-8") as fh:
        json.dump({"business_id": str(business_id) if business_id else None, "events": events}, fh, indent=2, default=str)

    print(f"N2BPROBE capture_written={_CAPTURE}")
    print(f"N2BPROBE inventory_events={len(events)}")
    for i, ev in enumerate(events):
        print(f"N2BPROBE event[{i}] executemany={ev['executemany']}")


if __name__ == "__main__":
    asyncio.run(main())

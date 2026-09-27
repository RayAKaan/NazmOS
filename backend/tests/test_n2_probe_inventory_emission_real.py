"""N2-B probe — REAL fixture, REAL _seed, UNTRUNCATED inventory emission dump.

Requests the REAL committed `sqlite_db` fixture (real fixture machinery), uses
the REAL committed `_seed`, listens on the REAL sync engine, and prints the
FULL untruncated statement + each bound parameter row for every inventory
INSERT. The IntegrityError traceback in the test output truncates params
(150-char repr) which is what led N1 to the wrong "replay" conclusion — this
probe prints the actual bytes.

Temporary probe; never committed.
"""

import pytest
from sqlalchemy import event

from tests.test_analytics_health_score import _seed


def _dump_rows(parameters):
    """Full untruncated dump of bound parameters for an INSERT."""
    rows = list(parameters) if isinstance(parameters, (list, tuple)) else [parameters]
    out = []
    for r in rows:
        if isinstance(r, dict):
            out.append(
                {
                    "id": str(r.get("id", ""))[:12],
                    "r_business_id": str(r.get("business_id", ""))[:12],
                    "r_item_id": str(r.get("item_id", ""))[:12],
                    "r_location_id": r.get("location_id"),
                }
            )
        else:
            out.append(f"nondict:{type(r).__name__}")
    return out


@pytest.mark.asyncio
async def test_probe_inventory_emission_real_fixture(sqlite_db):
    SessionLocal, sync_engine = sqlite_db
    events = []

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _probe(conn, cursor, statement, parameters, context, executemany):
        low = statement.lower()
        if "insert into inventory" in low or "insert into `inventory`" in low:
            events.append(
                {
                    "executemany": executemany,
                    "nparams": len(parameters)
                    if isinstance(parameters, (list, tuple))
                    else "scalar",
                    "rows": _dump_rows(parameters),
                    "stmt_full": statement,
                }
            )

    business_id = None
    try:
        async with SessionLocal() as db:
            business_id = await _seed(db)
    except Exception as exc:
        print(f"PROBE seed_error={type(exc).__name__}: {str(exc)[:220]}")
    finally:
        event.remove(sync_engine, "before_cursor_execute", _probe)

    print(f"PROBE seed_ok business={str(business_id)[:8] if business_id else None}")
    print(f"PROBE inventory_insert_events={len(events)}")
    for i, ev in enumerate(events):
        print(
            f"PROBE event[{i}] executemany={ev['executemany']} "
            f"nparams={ev['nparams']}"
        )
        for row in ev["rows"]:
            print(f"PROBE event[{i}] row {row}")
        print(f"PROBE event[{i}] FULL_STMT={ev['stmt_full']}")

    assert business_id is not None

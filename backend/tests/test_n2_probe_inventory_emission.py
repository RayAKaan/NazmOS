"""N2 probe — deterministically observe the REAL inventory INSERT emission.

Drives the REAL committed fixture generator (`tests.test_analytics_health_score.sqlite_db`)
via `anext` and the REAL committed seed helper (`_seed`), attaching a
`before_cursor_execute` listener that captures ONLY statements that actually
insert into `inventory`, then prints the FULL (untruncated) bound parameters.

No re-implementation of the seed or the fixture. Temporary file - deleted after
capture.
"""

import asyncio

from tests.test_analytics_health_score import _seed as real_seed
from tests.test_analytics_health_score import sqlite_db as sqlite_db_gen


def _rows_summary(parameters):
    """Minimal per-row summary; do NOT print full UUIDs."""
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


def _insert_row_tuples(statement):
    """Return the count of top-level `(?, ...)` row tuples in an INSERT.

    Multi-row INSERTs appear as `(?, ?, ...), (?, ?, ...)` — i.e. the comma
    followed by `(` right after a `)`.
    """
    import re

    return len(re.findall(r"\), \(", statement))


async def main():
    events = []

    def _probe_exec(conn, cursor, statement, parameters, context, executemany):
        low = statement.lower()
        if "insert into inventory" in low or "insert into `inventory`" in low:
            events.append(
                {
                    "executemany": executemany,
                    "nparams_total": len(parameters)
                    if isinstance(parameters, (list, tuple))
                    else "scalar",
                    "rows": _rows_summary(parameters),
                    "n_row_tuples": _insert_row_tuples(statement),
                    "stmt": statement,
                }
            )

    try:
        gen = sqlite_db_gen()
        SessionLocal, sync_engine = await gen.__anext__()
    except StopAsyncIteration:
        print("PROBE fixture_error: generator yielded nothing")
        return

    from sqlalchemy import event

    event.listen(sync_engine, "before_cursor_execute", _probe_exec)

    business_id = None
    try:
        async with SessionLocal() as db:
            business_id = await real_seed(db)
    except Exception as exc:
        print(f"PROBE seed_error={type(exc).__name__}: {str(exc)[:260]}")
    finally:
        event.remove(sync_engine, "before_cursor_execute", _probe_exec)
        await gen.aclose()

    print(f"PROBE seed_ok business={str(business_id)[:8] if business_id else None}")
    print(f"PROBE inventory_insert_events={len(events)}")
    for i, ev in enumerate(events):
        print(
            f"PROBE event[{i}] executemany={ev['executemany']} "
            f"nparams_total={ev['nparams_total']} n_row_tuples={ev['n_row_tuples']}"
        )
        for row in ev["rows"]:
            print(f"PROBE event[{i}] row {row}")
        print(f"PROBE event[{i}] stmt={ev['stmt']}")


if __name__ == "__main__":
    asyncio.run(main())

"""Non-destructive, evidence-driven repair + probe for the Phase 2 capture blocker.

Only prints integers and a strict allowlist of short fixed strings; nothing
that a path-masker or repr-masker can interfere with.
"""

import io
import os
import re
import sys

TARGET = r"H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED\backend\tests\test_n2d_probe_inventory_capture.py"


def main():
    with io.open(TARGET, "r", encoding="utf-8") as fh:
        src = fh.read()

    lines = src.splitlines()
    n_bind = sum(1 for ln in lines if ".bind" in ln)
    n_tup_bind = len(re.findall(r"sqlite_db\.bind\b", src))
    n_sync_engine = sum(1 for ln in lines if "sync_engine" in ln)
    n_tuple_destructure = sum(
        1 for ln in lines if re.search(r"(SessionLocal|SessionLocal,)\s*,\s*(sync_engine|sync_engine)\s*=", ln)
    )
    n_self_import = sum(1 for ln in lines if "import sqlite_db" in ln and "capture" in ln)
    n_emission_import = sum(1 for ln in lines if "test_n2_probe_inventory_emission" in ln)

    print(f"FACTS n_bind={n_bind} n_tup_bind={n_tup_bind} n_sync_engine={n_sync_engine}")
    print(f"FACTS n_tuple_destructure={n_tuple_destructure} n_self_import={n_self_import} n_emission_import={n_emission_import}")

    # Decide repair only from repository-verified evidence:
    # the emission sibling (committed contract) yields (SessionLocal, sync_engine)
    # tuple via its async generator; the capture test must destructure and hook
    # the engine. Do NOT invent .bind; do NOT create fake fixtures.
    changed = 0
    if n_tup_bind:
        # Replace only the malformed listen/remove targets.
        src = src.replace("event.listen(sqlite_db.bind,", "event.listen(sync_engine,")
        src = src.replace("event.remove(sqlite_db.bind,", "event.remove(sync_engine,")
        changed += 1
        with io.open(TARGET, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(src)
        print(f"REPAIR tup_bind_fixed={changed}")
    else:
        print(f"REPAIR noop tup_bind_already_absent")

    # Always re-verify after any change.
    with io.open(TARGET, "r", encoding="utf-8") as fh:
        src2 = fh.read()
    print(
        "VERIFY tup_bind="
        + str(len(re.findall(r"sqlite_db\.bind\b", src2)))
        + " sync_engine="
        + str(sum(1 for ln in src2.splitlines() if "sync_engine" in ln))
    )


if __name__ == "__main__":
    main()

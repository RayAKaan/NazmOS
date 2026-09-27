"""V1 Outcome Ledger — outcome/business-state capture (MASTER_PLAN sec 17).

The unified business-state target: ONE snapshot row per decision that binds
   decision  (deterministic, always authoritative)
   evidence  (capsule hash, model, provider, latency, risk_flags)
   outcome   (measured result, attached later, verified-flagged)

Purpose:
  * Give the Jev shadows a durable, schema-versioned SQLite capture so the
    learning loop (outcome_learning / outcome_feedback_contract) consumes
    VERIFIED outcomes only — never raw Jev output (MASTER_PLAN sec 8).
  * SQLite capture keeps the foundation DB-free/testable; the same schema
    maps 1:1 onto the Postgres `outcome_feedback` / `learned_outcomes`
    write path already in production.

Invariants enforced here:
  * Capture is ALWAYS best-effort (opening/writing the ledger never blocks or
    changes a decision). A locked/missing/invalid ledger is logged and skipped.
  * `schema_version = "v1"` is stamped on every row (COLUMNS definition).
  * A row records the deterministic decision as authoritative and the Jev
    suggestion as advisory; `source` distinguishes jev|fallback|disabled.
  * Outcome fields are UNKNOWN/NULL until a verified result is attached
    (`record_verified_result`); verified rows are the only rows the learning
    consumers read (`verified_outcomes`).
  * Idempotent under retry: replaying the same decision_key overwrites the
    same row rather than growing the ledger.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from typing import Any

logger = logging.getLogger("outcome_ledger")

OUTCOME_SCHEMA_VERSION = "v1"

COLUMNS: list[str] = [
    "decision_key",          # idempotency key (business:capability:deterministic)
    "recorded_at",           # ISO timestamp of capture
    "schema_version",        # OUTCOME_SCHEMA_VERSION
    "capability",            # Jev surface, e.g. recovery.rank
    "deterministic_decision",# authoritative decision (always wins)
    "jev_suggested",         # validated advisory suggestion (nullable)
    "source",                # jev | fallback | disabled
    "agree",                 # 1/0: Jev agreed with deterministic (or no suggestion)
    "risk_flags",            # JSON list
    "capsule_hash",          # evidence reference (opaque; no raw payload)
    "model",                 # model version
    "provider",              # provider label
    "latency_ms",            # consult latency at capture time
    "outcome_status",        # unknown|confirmed|partial|failed|rejected
    "verified",              # 1/0: measured & attributable
    "expected_impact_sar",   # nullable
    "actual_impact_sar",     # nullable
]

_CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS outcome_ledger_v1 (
    decision_key TEXT PRIMARY KEY,
    recorded_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    capability TEXT NOT NULL,
    deterministic_decision TEXT NOT NULL,
    jev_suggested TEXT,
    source TEXT NOT NULL,
    agree INTEGER NOT NULL,
    risk_flags TEXT NOT NULL,
    capsule_hash TEXT NOT NULL,
    model TEXT,
    provider TEXT,
    latency_ms REAL NOT NULL,
    outcome_status TEXT NOT NULL,
    verified INTEGER NOT NULL,
    expected_impact_sar REAL,
    actual_impact_sar REAL
)
"""


class OutcomeLedger:
    """Best-effort V1 outcome capture to a SQLite file.

    Use as a context manager or directly; every write is wrapped so capture
    friction can never block or change a decision.
    """

    def __init__(self, path: str | os.PathLike) -> None:
        self.path = str(path)

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.execute(_CREATE_SQL)
        return conn

    def record(
        self,
        *,
        decision_key: str,
        capability: str,
        deterministic_decision: str,
        source: str,
        jev_suggested: str | None = None,
        agree: bool = True,
        risk_flags: list[str] | None = None,
        capsule_hash: str = "",
        model: str | None = None,
        provider: str | None = None,
        latency_ms: float = 0.0,
    ) -> bool:
        """Append one decision row (idempotent on decision_key). Best-effort."""
        try:
            params = {
                "decision_key": decision_key,
                "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "schema_version": OUTCOME_SCHEMA_VERSION,
                "capability": capability,
                "deterministic_decision": deterministic_decision,
                "jev_suggested": jev_suggested,
                "source": source,
                "agree": 1 if agree else 0,
                "risk_flags": json.dumps(risk_flags or []),
                "capsule_hash": capsule_hash,
                "model": model,
                "provider": provider,
                "latency_ms": latency_ms,
                "outcome_status": "unknown",
                "verified": 0,
                "expected_impact_sar": None,
                "actual_impact_sar": None,
            }
            with self._connect() as conn:
                conn.execute(
                    f"""
                    INSERT INTO outcome_ledger_v1
                        ({", ".join(COLUMNS)})
                    VALUES
                        (:decision_key, :recorded_at, :schema_version, :capability,
                         :deterministic_decision, :jev_suggested, :source, :agree,
                         :risk_flags, :capsule_hash, :model, :provider, :latency_ms,
                         :outcome_status, :verified, :expected_impact_sar,
                         :actual_impact_sar)
                    ON CONFLICT (decision_key) DO UPDATE SET
                        recorded_at = excluded.recorded_at,
                        jev_suggested = excluded.jev_suggested,
                        source = excluded.source,
                        agree = excluded.agree,
                        risk_flags = excluded.risk_flags,
                        capsule_hash = excluded.capsule_hash,
                        model = excluded.model,
                        provider = excluded.provider,
                        latency_ms = excluded.latency_ms
                    """,
                    params,
                )
            return True
        except Exception as exc:  # best-effort: capture must never block
            logger.warning("outcome_ledger_record_failed: %s", exc)
            return False

    def record_verified_result(
        self,
        *,
        decision_key: str,
        outcome_status: str,
        verified: bool,
        actual_impact_sar: float | None = None,
        expected_impact_sar: float | None = None,
    ) -> bool:
        """Attach a measured, verified outcome to a previously captured row.

        Only verified=True rows are exposed to learning consumers
        (``verified_outcomes``). Best-effort.

        Phase 4H-O: the UPDATE is rowcount-aware — a verified outcome can only be
        claimed against an EXISTING captured row. If the WHERE clause touched
        zero rows (missing/duplicate-unsafe decision) the method returns False so
        no consumer can treat a phantom row as verified.
        """
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    UPDATE outcome_ledger_v1
                    SET outcome_status = :status,
                        verified = :verified,
                        actual_impact_sar = :actual,
                        expected_impact_sar = :expected
                    WHERE decision_key = :key
                    """,
                    {
                        "key": decision_key,
                        "status": outcome_status,
                        "verified": 1 if verified else 0,
                        "actual": actual_impact_sar,
                        "expected": expected_impact_sar,
                    },
                )
                if cur.rowcount == 0:
                    return False
            return True
        except Exception as exc:  # best-effort
            logger.warning("outcome_ledger_verify_failed: %s", exc)
            return False

    def row(self, decision_key: str) -> dict[str, Any] | None:
        """Readback for ONE decision row — confirms an attach actually landed.

        Best-effort; mirrors ``verified_outcomes`` semantics. Consumers must
        NOT treat a bare ``True`` from ``record``/``record_verified_result`` as
        proof a row exists: confirm via this readback instead.
        """
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                r = conn.execute(
                    "SELECT * FROM outcome_ledger_v1 WHERE decision_key = :key",
                    {"key": decision_key},
                ).fetchone()
            return self._row_dict(r) if r is not None else None
        except Exception as exc:
            logger.warning("outcome_ledger_row_failed: %s", exc)
            return None

    def verified_outcomes(self) -> list[dict[str, Any]]:
        """Rows with a measured verified outcome — the ONLY rows learning reads."""
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT * FROM outcome_ledger_v1
                    WHERE verified = 1
                    ORDER BY recorded_at DESC
                    """
                ).fetchall()
            return [self._row_dict(r) for r in rows]
        except Exception as exc:
            logger.warning("outcome_ledger_read_failed: %s", exc)
            return []

    def summary(self) -> dict[str, Any]:
        """Disaggregated totals over the captured business state."""
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                total = conn.execute(
                    "SELECT COUNT(*) AS n FROM outcome_ledger_v1"
                ).fetchone()["n"]
                verified = conn.execute(
                    "SELECT COUNT(*) AS n FROM outcome_ledger_v1 WHERE verified = 1"
                ).fetchone()["n"]
                dissent = conn.execute(
                    "SELECT COUNT(*) AS n FROM outcome_ledger_v1 WHERE agree = 0"
                ).fetchone()["n"]
                status_rows = conn.execute(
                    "SELECT outcome_status, COUNT(*) AS n FROM outcome_ledger_v1 "
                    "GROUP BY outcome_status"
                ).fetchall()
            return {
                "schema_version": OUTCOME_SCHEMA_VERSION,
                "total_captured": int(total),
                "verified": int(verified),
                "dissent": int(dissent),
                "by_outcome_status": {
                    r["outcome_status"]: int(r["n"]) for r in status_rows
                },
            }
        except Exception as exc:
            logger.warning("outcome_ledger_summary_failed: %s", exc)
            return {"schema_version": OUTCOME_SCHEMA_VERSION, "error": str(exc)}

    @staticmethod
    def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = {k: row[k] for k in row.keys()}
        d["agree"] = bool(d["agree"])
        d["verified"] = bool(d["verified"])
        try:
            d["risk_flags"] = json.loads(d["risk_flags"])
        except Exception:
            d["risk_flags"] = []
        return d


def derive_decision_key(*, business_id: str, capability: str, deterministic_decision: str) -> str:
    """Idempotency key: business:capability:deterministic-decision (sha256-prefixed)."""
    import hashlib

    composite = f"{business_id}:{capability}:{deterministic_decision}"
    return hashlib.sha256(composite.encode()).hexdigest()[:24]
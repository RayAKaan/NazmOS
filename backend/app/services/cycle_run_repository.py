"""Durable Postgres repository for Business Improvement Loop runs (Phase 4B).

Adapter between the DB-free ``business_loop.cycle.CycleRepository`` seam and the
``cycle_runs`` table (migration ``ff14_cycle_runs``). Lives OUTSIDE
``app.services.business_loop`` so the loop package stays DB-free by design.

Durability contract (PHASE_4A_RUNTIME_CONTRACT_REPORT.md):
    * lossless round-trip through ``CycleRun.serialize()`` (all 21 stage states)
    * idempotent create on ``(business_id, cycle_id)`` — a duplicate trigger never
      creates a second row (unique constraint + INSERT ... ON CONFLICT DO NOTHING)
    * optimistic concurrency via the ``version`` column: a save against a stale
      version raises ``CycleRunConflictError`` instead of silently overwriting
    * terminal protection: once ``completed`` is true the row is immutable
      (a later save that would change it raises ``CycleRunConflictError``)
    * tenant isolation via Postgres RLS on ``business_id`` (defense-in-depth; the
      caller's session already carries ``SET LOCAL app.current_tenant_id``)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import CycleRunModel
from app.services.business_loop.cycle import CycleRun, CycleRepository, CycleRunConflictError, CycleStageState
from app.services.business_loop.contracts import CycleStage


def _model_to_run(row: CycleRunModel) -> CycleRun:
    """Rehydrate a domain CycleRun from a persisted row (lossless per 4A)."""
    stages = [
        CycleStageState(
            stage=CycleStage(s["stage"]),
            status=s.get("status", "pending"),
            attempts=int(s.get("attempts", 0)),
            error=s.get("error", ""),
            started_at=s.get("started_at", ""),
            finished_at=s.get("finished_at", ""),
        )
        for s in (row.stages or [])
    ]
    created_at = row.created_at
    if isinstance(created_at, datetime):
        created = created_at.astimezone(timezone.utc).isoformat(timespec="seconds")
    else:
        created = str(created_at or "")
    run = CycleRun(
        cycle_id=row.cycle_id,
        tenant_id=row.tenant_id,
        business_id=str(row.business_id),
        trigger=row.trigger,
        trigger_token=row.trigger_token or "",
        created_at=created,
        starting_state_version=row.starting_state_version or "",
        evidence_watermark=row.evidence_watermark or "",
        stages=stages,
        stage_index=int(row.stage_index or 0),
        completed=bool(row.completed),
        last_error=row.last_error or "",
        state_output=dict(row.state_output or {}),
        _version=int(row.version or 0),
    )
    # Long-lived observability timestamp for the read-only console (Phase 4G).
    # Not part of the domain header; attached from the persisted row only.
    updated = row.updated_at
    if isinstance(updated, datetime):
        run._updated_at = updated.astimezone(timezone.utc).isoformat(timespec="seconds")
    else:
        run._updated_at = str(updated or "")
    return run


class PostgresCycleRepository(CycleRepository):
    """Async durable repository over the ``cycle_runs`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load(self, business_id: str, cycle_id: str) -> CycleRun | None:
        row = (
            await self._session.execute(
                select(CycleRunModel).where(
                    CycleRunModel.business_id == UUID(str(business_id)),
                    CycleRunModel.cycle_id == cycle_id,
                )
            )
        ).scalar_one_or_none()
        return _model_to_run(row) if row else None

    async def save(self, run: CycleRun) -> None:
        stages_json: list[dict[str, Any]] = [
            {
                "stage": s.stage.value,
                "status": s.status,
                "attempts": s.attempts,
                "error": s.error,
                "started_at": s.started_at,
                "finished_at": s.finished_at,
            }
            for s in run.stages
        ]
        state_json = {k: v for k, v in run.state_output.items() if not k.startswith("_")}

        existing = (
            await self._session.execute(
                select(CycleRunModel).where(
                    CycleRunModel.business_id == UUID(str(run.business_id)),
                    CycleRunModel.cycle_id == run.cycle_id,
                )
            )
        ).scalar_one_or_none()

        if existing is None:
            await self._insert_new(run, stages_json, state_json)
            return

        # Terminal protection: a completed run is immutable.
        if existing.completed:
            if not run.completed and _differs(existing, run):
                raise CycleRunConflictError(
                    f"cycle {run.cycle_id} is completed (immutable)"
                )
            run._version = int(existing.version or 0)
            return  # idempotent re-save of an already-completed run

        # Optimistic concurrency: the UPDATE is accepted only when the persisted
        # version still matches the version the caller loaded (_version). A
        # concurrently-advanced row fails the predicate (rowcount 0) rather than
        # being silently overwritten.
        expected = run._version or int(existing.version or 0)
        result = await self._session.execute(
            update(CycleRunModel)
            .where(
                CycleRunModel.business_id == existing.business_id,
                CycleRunModel.cycle_id == existing.cycle_id,
                CycleRunModel.version == expected,
                CycleRunModel.completed.is_(False),
            )
            .values(
                stage_index=run.stage_index,
                completed=run.completed,
                last_error=run.last_error,
                state_output=state_json,
                stages=stages_json,
                starting_state_version=run.starting_state_version,
                evidence_watermark=run.evidence_watermark,
                version=expected + 1,
                updated_at=func.now(),
            )
        )
        if result.rowcount == 0:
            await self._session.rollback()
            raise CycleRunConflictError(f"cycle {run.cycle_id} changed concurrently")
        run._version = expected + 1
        await self._session.commit()

    async def _insert_new(
        self, run: CycleRun, stages_json: list[dict[str, Any]], state_json: dict[str, Any]
    ) -> None:
        values = {
            "business_id": UUID(str(run.business_id)),
            "cycle_id": run.cycle_id,
            "tenant_id": run.tenant_id,
            "trigger": run.trigger,
            "trigger_token": run.trigger_token,
            "created_at": _as_utc(run.created_at),
            "starting_state_version": run.starting_state_version,
            "evidence_watermark": run.evidence_watermark,
            "stage_index": run.stage_index,
            "completed": run.completed,
            "last_error": run.last_error,
            "state_output": state_json,
            "stages": stages_json,
        }

        try:
            # SQLite (dev/tests): no ON CONFLICT DO NOTHING for uuid default.
            dialect = self._session.get_bind().dialect.name
            if dialect == "postgresql":
                stmt = (
                    pg_insert(CycleRunModel)
                    .values(**values)
                    .on_conflict_do_nothing(index_elements=["business_id", "cycle_id"])
                )
                await self._session.execute(stmt)
            else:
                await self._session.execute(CycleRunModel.__table__.insert().values(**values))
            await self._session.commit()
        except IntegrityError:
            # Duplicate trigger raced in: already persisted, treat as idempotent.
            await self._session.rollback()
        # Pin the caller's version so a subsequent save guards correctly (both
        # for a fresh row and for a row that won the race against us).
        row = (
            await self._session.execute(
                select(CycleRunModel).where(
                    CycleRunModel.business_id == values["business_id"],
                    CycleRunModel.cycle_id == run.cycle_id,
                )
            )
        ).scalar_one_or_none()
        run._version = int(row.version or 0) if row else 1

    async def all(self, business_id: str) -> list[CycleRun]:
        """Tenant-scoped listing for the read-only runtime console (4G)."""
        rows = (
            await self._session.execute(
                select(CycleRunModel)
                .where(CycleRunModel.business_id == UUID(str(business_id)))
                .order_by(CycleRunModel.created_at.desc())
            )
        ).scalars().all()
        return [_model_to_run(r) for r in rows]

    async def page(
        self, business_id: str, *, limit: int = 20, offset: int = 0
    ) -> tuple[list[CycleRun], int]:
        """Bounded, deterministic listing for the 4G read-only console.

        Ordering is stable: ``created_at DESC`` then ``cycle_id ASC`` so two
        cycles created in the same second never flip between pages. Returns
        ``(runs, total)`` where total counts every run for the business.
        """
        base = select(CycleRunModel).where(CycleRunModel.business_id == UUID(str(business_id)))
        total = int(
            (
                await self._session.execute(
                    select(func.count()).select_from(base.subquery())
                )
            ).scalar_one()
        )
        rows = (
            await self._session.execute(
                base.order_by(CycleRunModel.created_at.desc(), CycleRunModel.cycle_id.asc())
                .offset(offset)
                .limit(limit)
            )
        ).scalars().all()
        return [_model_to_run(r) for r in rows], total

    async def outcome_keys(self, business_id: str) -> set[str]:
        """Union of OutcomeLedger keys referenced by this business's cycle runs.

        Scoping surface for the V1 OutcomeLedger (which has no tenant column):
        the ``outcome_key`` persisted with each run's ``outcome_attachment`` /
        ``outcome_recorded`` is derived from ``(tenant, execution_key,
        recommendation)``, so filtering verified rows by this set exposes ONLY
        this business's linked outcomes — unrelated legacy rows stay invisible.
        """
        rows = (
            await self._session.execute(
                select(CycleRunModel.state_output).where(
                    CycleRunModel.business_id == UUID(str(business_id))
                )
            )
        ).scalars().all()
        keys: set[str] = set()
        for state_output in rows:
            if not isinstance(state_output, dict):
                continue
            for field in ("outcome_attachment", "outcome_recorded"):
                attachment = state_output.get(field)
                if isinstance(attachment, dict) and attachment.get("outcome_key"):
                    keys.add(str(attachment["outcome_key"]))
        return keys


def _differs(existing: CycleRunModel, run: CycleRun) -> bool:
    return (
        int(existing.stage_index or 0) != run.stage_index
        or bool(existing.completed) != run.completed
        or (existing.last_error or "") != (run.last_error or "")
    )


def _as_utc(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
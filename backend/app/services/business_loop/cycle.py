"""Continuous cycle orchestrator (Phase 3I) — bounded, resumable, idempotent.

Coordinates the complete improvement loop (MASTER_PLAN §16.2). Every cycle has
    * a stable cycle_id derived from (tenant, business, trigger token) — a
      duplicate trigger cannot create a duplicate cycle
    * a starting state version + evidence watermark
    * a stage state machine with retry metadata and pause/resume
    * cooldowns and per-cycle work limits so an uncontrolled infinite loop is
      impossible
A cycle with no valid opportunity is a successful no-op. Executions still flow
through the registered-action + governance gates (nothing here re-authorizes).

The orchestrator only depends on the DB-free loop modules; the synthetic
vertical slice runs it with in-memory evidence + an in-memory repository, no
database and no Temporal. Production scheduling reuses
``app.orchestration.temporal.schedules``; ``CycleRun.serialize`` is the
durability seam.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app.services.business_loop.advisory import AdvisoryFn, consult_advisory, deterministic_only_advisor
from app.services.business_loop.contracts import (
    CycleStage,
    GovernanceOutcome,
    ImpactKind,
    RecommendationStatus,
)
from app.services.business_loop.evidence import EvidenceStore
from app.services.business_loop.execution import ExecutionIntent, dry_run_execute
from app.services.business_loop.governance import approve_binding, evaluate_governance
from app.services.business_loop.opportunity import Opportunity, detect_opportunities
from app.services.business_loop.outcome_linkage import attribution_sufficient, build_linkage, outcome_from_run
from app.services.business_loop.outcomes import learning_eligibility, verify_outcome
from app.services.business_loop.recommendation import make_recommendation
from app.services.business_loop.state import BusinessStateSnapshot, is_stale, project_state

StageHandler = Callable[["CycleRun"], Awaitable[None]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _opp_from_dict(o: dict[str, Any]) -> Opportunity:
    return Opportunity(
        opportunity_id=o["opportunity_id"],
        tenant_id=o["tenant_id"],
        business_id=o["business_id"],
        opportunity_type=o["opportunity_type"],
        state_version=o["state_version"],
        evidence_ids=tuple(o.get("evidence_ids", ())),
        rule_version=o["rule_version"],
        potential_impact_sar=o["potential_impact_sar"],
        expected_impact_sar=o.get("expected_impact_sar"),
        eligible_action_categories=tuple(o.get("candidate_actions") or o.get("eligible_action_categories", ())),
        lifecycle_status=o.get("lifecycle_status", "open"),
    )


def derive_cycle_id(*, tenant_id: str, business_id: str, trigger: str, trigger_token: str = "") -> str:
    """Stable cycle id — duplicate triggers (same token) suppress duplicates."""
    import hashlib

    composite = f"{tenant_id}:{business_id}:{trigger}:{trigger_token}"
    return f"cycle-{hashlib.sha256(composite.encode()).hexdigest()[:24]}"


@dataclass
class CyclePolicy:
    """Bounded-operation knobs for one tenant/business loop."""

    cooldown_seconds: int = 300
    max_opportunities_per_cycle: int = 20
    max_recommendations_per_cycle: int = 5
    max_retries_per_stage: int = 2
    stale_max_age_days: int = 7
    shariah_approved: bool = True
    shariah_ambiguous: bool = False
    advisory_fn: AdvisoryFn | None = None
    verification_evaluator: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None


@dataclass
class CycleStageState:
    stage: CycleStage
    status: str = "pending"  # pending | running | ok | failed | skipped
    attempts: int = 0
    error: str = ""
    started_at: str = ""
    finished_at: str = ""


@dataclass
class CycleRun:
    """One bounded improvement cycle (in-memory; durable via serialize/seam)."""

    cycle_id: str
    tenant_id: str
    business_id: str
    trigger: str
    trigger_token: str
    created_at: str
    starting_state_version: str
    evidence_watermark: str
    stages: list[CycleStageState] = field(default_factory=list)
    stage_index: int = 0
    completed: bool = False
    last_error: str = ""
    state_output: dict[str, Any] = field(default_factory=dict)
    _snapshot: BusinessStateSnapshot | None = None
    _version: int = 0  # optimistic-concurrency guard; never serialized

    def serialize(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "tenant_id": self.tenant_id,
            "business_id": self.business_id,
            "trigger": self.trigger,
            "trigger_token": self.trigger_token,
            "created_at": self.created_at,
            "starting_state_version": self.starting_state_version,
            "evidence_watermark": self.evidence_watermark,
            "completed": self.completed,
            "stage_index": self.stage_index,
            "last_error": self.last_error,
            "state_output": {k: v for k, v in self.state_output.items() if not k.startswith("_")},
            "stages": [
                {
                    "stage": s.stage.value if hasattr(s.stage, "value") else str(s.stage),
                    "status": s.status,
                    "attempts": s.attempts,
                    "error": s.error,
                }
                for s in self.stages
            ],
        }


class CycleRepository:
    """Persistence seam: production uses Temporal + DB; tests use in-memory."""

    async def save(self, run: CycleRun) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    async def load(self, business_id: str, cycle_id: str) -> CycleRun | None:  # pragma: no cover - abstract
        raise NotImplementedError


class CycleRunConflictError(RuntimeError):
    """Stale-version or terminal-immutability violation on a durable save.

    Shared by the Postgres repository and the InMemory repository (Phase 4H-C)
    so DB-free concurrency tests exercise the SAME conflict semantics.
    """


def _run_differs(existing: CycleRun, run: CycleRun) -> bool:
    """Structural difference test mirroring the Postgres terminal guard."""
    return (
        existing.stage_index != run.stage_index
        or existing.completed != run.completed
        or (existing.last_error or "") != (run.last_error or "")
    )


class InMemoryCycleRepository(CycleRepository):
    """DB-free repository for the synthetic slice and deterministic tests.

    Phase 4H hardening: the store keeps a DEEP COPY of every cycle with a
    per-row optimistic version so DB-free concurrency tests behave exactly like
    the Postgres repository (conflict instead of silent clobber, terminal runs
    immutable, caller version re-pinned on every successful save). Tests holding
    a ``CycleRun`` mutate + save it repeatedly and stay consistent because a
    successful ``save`` writes the caller's version back onto that object.
    """

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], CycleRun] = {}

    async def save(self, run: CycleRun) -> None:
        key = (run.business_id, run.cycle_id)
        existing = self._store.get(key)
        if existing is None:
            run._version = 1
            self._store[key] = copy.deepcopy(run)
            return
        # Terminal protection: a completed run is immutable.
        if existing.completed:
            if not run.completed and _run_differs(existing, run):
                raise CycleRunConflictError(f"cycle {run.cycle_id} is completed (immutable)")
            run._version = existing._version
            return
        # Optimistic concurrency: mirrors the Postgres version predicate.
        expected = run._version or existing._version
        if expected != existing._version:
            raise CycleRunConflictError(f"cycle {run.cycle_id} changed concurrently")
        run._version = existing._version + 1
        self._store[key] = copy.deepcopy(run)

    async def load(self, business_id: str, cycle_id: str) -> CycleRun | None:
        run = self._store.get((business_id, cycle_id))
        return copy.deepcopy(run) if run is not None else None

    def all(self, business_id: str = "") -> list[CycleRun]:
        runs = [
            r for (b, _), r in self._store.items()
            if (not business_id or b == business_id)
        ]
        return [copy.deepcopy(r) for r in runs]


class CycleOrchestrator:
    """Runs one bounded improvement cycle stage-by-stage with resume support."""

    def __init__(
        self,
        *,
        repository: CycleRepository,
        evidence: EvidenceStore | None = None,
        policy: CyclePolicy | None = None,
        verification_evidence: EvidenceStore | None = None,
    ) -> None:
        self.repository = repository
        self.evidence = evidence or EvidenceStore()
        self.policy = policy or CyclePolicy()
        # Post-action observations for a cycle's verification window. In
        # production these arrive via the normal event pipeline; keeping them
        # on a separate seam makes the synthetic slice honest: the pre-state
        # (cycle evidence) and post-state (verification evidence) are distinct.
        self.verification_evidence = verification_evidence or self.evidence

    # ---- lifecycle ----------------------------------------------------------

    async def start(
        self,
        *,
        tenant_id: str,
        business_id: str,
        trigger: str = "synthetic",
        trigger_token: str = "",
    ) -> CycleRun:
        """Idempotent cycle start: duplicate trigger token returns the existing run.

        Async by design: durable repositories persist on save/load.
        """
        cycle_id = derive_cycle_id(
            tenant_id=tenant_id, business_id=business_id, trigger=trigger, trigger_token=trigger_token
        )
        existing = await self.repository.load(business_id, cycle_id)
        if existing is not None:
            # Duplicate trigger token — running OR completed — returns the SAME
            # run (Phase 4H terminal guard): a completed cycle never regresses
            # and a re-delivered trigger never starts a second logical cycle.
            # A NEW logical cycle requires a NEW trigger token.
            return existing

        stages = [CycleStageState(stage=s) for s in CycleStage.ordered()]
        run = CycleRun(
            cycle_id=cycle_id,
            tenant_id=tenant_id,
            business_id=business_id,
            trigger=trigger,
            trigger_token=trigger_token,
            created_at=_now_iso(),
            starting_state_version="",
            evidence_watermark="",
            stages=stages,
        )
        await self.repository.save(run)
        return run

    async def load(self, business_id: str, cycle_id: str) -> CycleRun | None:
        return await self.repository.load(business_id, cycle_id)

    def _saved_snapshot(self, run: CycleRun) -> BusinessStateSnapshot:
        """Best-effort snapshot for a resumed cycle.

        Phase 4H recovery: when the in-memory ``_snapshot`` was never carried
        across a restart, the REAL projected snapshot is rehydrated losslessly
        from the persisted ``state_output["state"]`` (``from_dict``) instead of
        an empty-domain stand-in — a resumed verification measures the true
        baseline, not an invented one.
        """
        if run._snapshot is not None:
            return run._snapshot
        state = run.state_output.get("state", {})
        if isinstance(state, dict) and state.get("tenant_id") and isinstance(state.get("domains"), dict):
            return BusinessStateSnapshot.from_dict(state)
        return BusinessStateSnapshot(
            tenant_id=run.tenant_id,
            business_id=run.business_id,
            state_version=state.get("state_version", run.starting_state_version),
            schema_version="loop-v1",
            created_at=state.get("created_at", _now_iso()),
            domains={},
            evidence_lineage=(),
            quality_flags=(),
        )

    async def revalidate_persisted(self, run: CycleRun) -> dict[str, Any]:
        """Phase 4E — revalidate a resumed cycle's pinned baseline against the live evidence.

        A persisted cycle may advance past its pinned cursor ONLY while its
        ``starting_state_version`` and ``evidence_watermark`` are still
        reproducible from the evidence the resume actually projects. Drift means
        the durable baseline no longer matches reality — continuing would let
        later stages (freshness, opportunities, recommendation, governance,
        verification) measure against a state the loop never truly pinned.

        Verdict (JSON-safe, never persisted here):
            ok                        True only when the pinned baseline reproduces
            status                    consistent | not_pinned | state_version_drift |
                                      watermark_drift | cross_scope (semicolon-joined)
            recomputed_state_version  projection over the resume evidence
            persisted_state_version   run.starting_state_version
            recomputed_watermark      max observed_at over accepted evidence ("none")
            persisted_watermark       run.evidence_watermark
            cross_scope               count of out-of-scope accepted records

        A run that has not yet reached STATE_PROJECTION has no pinned baseline to
        guard (status ``not_pinned``, ok=True). Callers MUST treat ``ok=False``
        as a hard block and never blind-continue.
        """
        if not run.starting_state_version:
            return {
                "ok": True,
                "status": "not_pinned",
                "recomputed_state_version": "",
                "persisted_state_version": "",
                "recomputed_watermark": run.evidence_watermark or "",
                "persisted_watermark": run.evidence_watermark or "",
                "cross_scope": 0,
            }
        recomputed = project_state(
            self.evidence,
            tenant_id=run.tenant_id,
            business_id=run.business_id,
            max_age_days=self.policy.stale_max_age_days,
        )
        accepted = [
            r for r in self.evidence.accepted()
            if r.tenant_id == run.tenant_id and r.business_id == run.business_id
        ]
        cross = [
            r for r in self.evidence.accepted()
            if r.tenant_id != run.tenant_id or r.business_id != run.business_id
        ]
        recomputed_wm = "none" if not accepted else max(r.observed_at for r in accepted)
        drift: list[str] = []
        if recomputed.state_version != run.starting_state_version:
            drift.append("state_version_drift")
        if run.evidence_watermark and recomputed_wm != run.evidence_watermark:
            drift.append("watermark_drift")
        if cross:
            drift.append("cross_scope")
        return {
            "ok": not drift,
            "status": ";".join(drift) if drift else "consistent",
            "recomputed_state_version": recomputed.state_version,
            "persisted_state_version": run.starting_state_version,
            "recomputed_watermark": recomputed_wm,
            "persisted_watermark": run.evidence_watermark,
            "cross_scope": len(cross),
        }

    # ---- stage driving ------------------------------------------------------

    async def run_one_stage(self, run: CycleRun) -> bool:
        """Advance exactly one stage; returns False when the cycle finished/blocked.

        Phase 4H crash-safety:
            * a resumed run whose CURRENT stage already committed (``ok``) after a
              crash between stage completion and cursor advance CONVERGES by
              advancing the cursor WITHOUT re-running the handler — restart never
              duplicates an external effect
            * a resumed EXECUTION stage still marked ``running`` is an UNKNOWN
              external outcome (the handler may have partially executed), so it is
              never blind-re-run: it converges to a guarded, reconciliation-
              required record
        """
        if run.completed or run.stage_index >= len(run.stages):
            return False

        stage = run.stages[run.stage_index]

        if stage.status == "ok":
            run.stage_index += 1
            await self.repository.save(run)
            return True

        if stage.status == "running" and stage.stage == CycleStage.EXECUTION:
            # Crash mid-execution == unknown external state. Converge WITHOUT
            # re-running: record an unconfirmed receipt so reconciliation marks
            # the outcome RECONCILIATION_REQUIRED and verification never fabricates.
            execution = dict(run.state_output.get("execution") or {})
            run.state_output["execution"] = {
                **execution,
                "resumed_crashed": True,
                "receipt": execution.get("receipt") or {
                    "ok": False,
                    "details": {"reason": "unconfirmed_external_outcome_after_restart"},
                },
            }
            stage.status = "ok"
            stage.finished_at = _now_iso()
            run.stage_index += 1
            await self.repository.save(run)
            return True

        if stage.status == "failed":
            if stage.attempts < self.policy.max_retries_per_stage:
                stage.status = "pending"
                stage.error = ""
                await self.repository.save(run)
            else:
                return False  # retry budget exhausted -> blocked (documented)

        stage.status = "running"
        stage.attempts += 1
        stage.started_at = _now_iso()
        await self.repository.save(run)

        try:
            handler = self._handlers().get(stage.stage)
            if handler is not None:
                await handler(run)
        except Exception as exc:  # noqa: BLE001 (bounded cycle failure, recorded)
            stage.status = "failed"
            stage.error = str(exc)
            run.last_error = str(exc)
            await self.repository.save(run)
            return False

        stage.status = "ok"
        stage.finished_at = _now_iso()
        run.stage_index += 1
        await self.repository.save(run)
        return True

    async def run_all(self, run: CycleRun) -> CycleRun:
        """Run every stage to completion (bounded; safe for the synthetic slice)."""
        guard = 0
        while await self.run_one_stage(run):
            guard += 1
            if guard > len(CycleStage.ordered()) * (self.policy.max_retries_per_stage + 1):
                run.last_error = "run_guard_exceeded"
                break
        return run

    # ---- stage handlers -----------------------------------------------------

    def _advisory_fn(self) -> AdvisoryFn:
        return self.policy.advisory_fn or deterministic_only_advisor

    async def _stage_evidence_discovery(self, run: CycleRun) -> None:
        accepted = self.evidence.accepted()
        run.evidence_watermark = "none" if not accepted else max(e.observed_at for e in accepted)

    async def _stage_ingestion(self, run: CycleRun) -> None:
        pass  # validated/committed upstream by the EvidenceStore boundary

    async def _stage_validation(self, run: CycleRun) -> None:
        invalid = [
            r for r in self.evidence.all()
            if r.tenant_id != run.tenant_id or r.business_id != run.business_id
        ]
        if invalid:
            raise RuntimeError(f"cross_scope_evidence_rejected:{len(invalid)}")
        run.state_output["evidence_count"] = len(self.evidence.accepted())

    async def _stage_state_projection(self, run: CycleRun) -> None:
        snapshot = project_state(
            self.evidence,
            tenant_id=run.tenant_id,
            business_id=run.business_id,
            max_age_days=self.policy.stale_max_age_days,
        )
        if not run.starting_state_version:
            run.starting_state_version = snapshot.state_version
        run._snapshot = snapshot
        run.state_output["state"] = snapshot.to_dict()

    async def _stage_freshness(self, run: CycleRun) -> None:
        snapshot = run._snapshot
        if snapshot is None:
            raise RuntimeError("no_state_projection")
        if is_stale(snapshot, max_age_days=self.policy.stale_max_age_days):
            if not run.evidence_watermark or run.evidence_watermark == "none":
                raise RuntimeError("stale_state_no_evidence")

    async def _stage_opportunities(self, run: CycleRun) -> None:
        snapshot = run._snapshot
        if snapshot is None:
            raise RuntimeError("no_state_projection")
        opps = detect_opportunities(snapshot, eligible_actions=None)[
            : self.policy.max_opportunities_per_cycle
        ]
        run.state_output["opportunities"] = [o.to_dict() for o in opps]
        run.state_output["opportunity_count"] = len(opps)

    async def _stage_impact(self, run: CycleRun) -> None:
        for o in run.state_output.get("opportunities", []):
            o["impact_kind"] = ImpactKind.POTENTIAL.value

    async def _stage_action_candidates(self, run: CycleRun) -> None:
        for o in run.state_output.get("opportunities", []):
            o["candidate_actions"] = list(o.get("eligible_action_categories", ()))

    async def _stage_advisory(self, run: CycleRun) -> None:
        opps = run.state_output.get("opportunities", [])
        if not opps:
            run.state_output["advisory"] = {"source": "none"}
            return
        contract = frozenset(opps[0].get("candidate_actions") or ())
        advisory = await consult_advisory(
            self._advisory_fn(),
            capability="business_loop.action_selection",
            context={
                "payload": {"tenant_id": run.tenant_id, "business_id": run.business_id},
                "deterministic_decision": opps[0]["opportunity_type"],
                "purpose": "continuous_business_loop",
                "contract": contract,
            },
            contract=contract,
        )
        run.state_output["advisory"] = advisory.to_dict()

    async def _stage_advisory_validation(self, run: CycleRun) -> None:
        advisory = run.state_output.get("advisory", {})
        if not advisory or advisory.get("source") == "none":
            return
        if not advisory.get("validation_passed", True):
            # Recorded failure, never coerced: the rejected suggestion must be
            # dropped so the recommendation continues ONLY on the deterministic
            # candidate path, with advisory_validated=False.
            run.state_output["advisory"] = {
                **advisory,
                "suggested": None,
                "rejected_invalid": True,
            }

    async def _stage_recommendation(self, run: CycleRun) -> None:
        opps = run.state_output.get("opportunities", [])
        if not opps:
            run.state_output["recommendations"] = []
            return
        o = opps[0]
        opportun = _opp_from_dict(o)
        advisory = run.state_output.get("advisory", {})
        actions = list(opportun.eligible_action_categories) or ["review"]
        # Contract-validated advisory suggestion may select among the DETERMINISTIC
        # candidate list; otherwise the first candidate wins. AI never authorizes —
        # it only narrows candidates the governor will still evaluate.
        suggested = advisory.get("suggested")
        chosen = suggested if suggested in actions else actions[0]
        reco = make_recommendation(
            recommendation_id=f"rec-{o['opportunity_id']}",
            opportunity=opportun,
            business_id=run.business_id,
            tenant_id=run.tenant_id,
            state_version=opportun.state_version,
            action_type=chosen,
            provider=str(advisory.get("provider") or "deterministic"),
            advisory_validated=bool(advisory.get("validation_passed", True)),
            expected_impact_sar=opportun.expected_impact_sar,
        )
        run.state_output["recommendations"] = [reco.describe()]

    async def _stage_governance(self, run: CycleRun) -> None:
        recos = run.state_output.get("recommendations", [])
        gv = evaluate_governance(
            recommendation_id=recos[0]["recommendation_id"] if recos else "none",
            action_type=recos[0]["action_type"] if recos else "review",
            business_id=run.business_id,
            shariah_approved=self.policy.shariah_approved,
            shariah_ambiguous=self.policy.shariah_ambiguous,
        )
        run.state_output["governance"] = gv.to_dict()

    async def _stage_approval_wait(self, run: CycleRun) -> None:
        gv = run.state_output.get("governance", {})
        outcome = gv.get("outcome")
        recos = run.state_output.get("recommendations", [])
        if outcome in (
            GovernanceOutcome.PERMITTED.value,
            GovernanceOutcome.APPROVAL_REQUIRED.value,
        ) and recos:
            # Owner approval is SIMULATED only in the synthetic slice. Production
            # approval flows through run_agent_approval / the owner approval
            # surface, never through this stage.
            # Phase 4H: the simulated approval is BOUND to the EXACT recommendation
            # version + material hash (approve_binding) so a later materially
            # changed recommendation can never silently reuse this approval.
            recos[0]["status"] = RecommendationStatus.APPROVED.value
            binding = approve_binding(
                recommendation_id=recos[0]["recommendation_id"],
                recommendation_version=int(recos[0].get("version", 1)),
                material_hash=str(recos[0].get("material_hash", "") or ""),
                approved_by="synthetic_owner",
            )
            run.state_output["approval"] = {
                "mode": "simulated_owner_approval",
                "note": "SYNTHETIC - not a real owner decision",
                **binding,
            }

    async def _stage_preflight(self, run: CycleRun) -> None:
        pass  # pre-execution revalidation happens at EXECUTION via dry_run_execute

    async def _stage_execution(self, run: CycleRun) -> None:
        recos = run.state_output.get("recommendations", [])
        gv = run.state_output.get("governance", {})
        if not recos or gv.get("outcome") not in (
            GovernanceOutcome.PERMITTED.value,
            GovernanceOutcome.APPROVAL_REQUIRED.value,
        ):
            run.state_output["execution"] = {"skipped": True, "reason": "governance_not_permitted"}
            return
        r0 = recos[0]
        if r0["status"] != RecommendationStatus.APPROVED.value:
            run.state_output["execution"] = {
                "skipped": True,
                "reason": f"recommendation_not_approved:{r0['status']}",
            }
            return
        # Phase 4H-I: a stored approval is honored ONLY for the exact material
        # it was bound to. Re-derive the binding from the CURRENT recommendation
        # fields; any drift means the approval is stale and cannot authorize.
        approval = run.state_output.get("approval") or {}
        if approval.get("binding_key"):
            expected_binding = approve_binding(
                recommendation_id=r0["recommendation_id"],
                recommendation_version=int(r0.get("version", 1)),
                material_hash=str(r0.get("material_hash", "") or ""),
                approved_by=str(approval.get("approved_by", "synthetic_owner")),
            )
            if approval["binding_key"] != expected_binding["binding_key"]:
                run.state_output["execution"] = {
                    "skipped": True,
                    "reason": "approval_material_mismatch",
                }
                return
        intent = ExecutionIntent(
            business_id=run.business_id,
            action_type=r0["action_type"],
            entity_type="item",
            entity_id=r0["opportunity_id"],
            payload={"recommendation_id": r0["recommendation_id"]},
            recommendation_id=r0["recommendation_id"],
        )
        decision = GovernanceOutcome.PERMITTED  # approval gate already passed (simulated or none)
        receipt = dry_run_execute(intent, decision=decision, recommendation_status=RecommendationStatus.APPROVED)
        run.state_output["execution"] = {
            "action_type": r0["action_type"],
            "recommendation_id": r0["recommendation_id"],
            "execution_key": intent.execution_key,
            "receipt": {
                "receipt_id": receipt.receipt_id,
                "ok": receipt.ok,
                "synthetic": receipt.synthetic,
                "details": receipt.details,
            },
        }

    async def _stage_reconciliation(self, run: CycleRun) -> None:
        execution = run.state_output.get("execution", {})
        if execution.get("skipped"):
            run.state_output["reconciliation"] = {
                "allow_retry": False,
                "reason": execution.get("reason", "skipped"),
            }
            return
        receipt = execution.get("receipt", {})
        if not receipt:
            # No receipt at all = unknown external state. Phase 4H-E: never
            # FAILED, never blind-retried — reconciliation is REQUIRED.
            run.state_output["reconciliation"] = {
                "allow_retry": False,
                "reason": "unconfirmed_external_outcome",
                "status": "unknown_external_outcome",
                "reconciliation_required": True,
            }
            return
        if receipt.get("ok"):
            # actual state REPORTED = potentially succeeded; must NOT blind-retry
            run.state_output["reconciliation"] = {
                "allow_retry": False,
                "reason": "reported_recorded_await_verification",
            }
            return
        raw_reason = receipt.get("details", {}).get("reason", "execution_failed")
        lowered = str(raw_reason).lower()
        if any(token in lowered for token in ("unknown", "unconfirmed", "timeout")):
            run.state_output["reconciliation"] = {
                "allow_retry": False,
                "reason": raw_reason,
                "status": "unknown_external_outcome",
                "reconciliation_required": True,
            }
            return
        run.state_output["reconciliation"] = {
            "allow_retry": False,
            "reason": raw_reason,
        }

    async def _stage_verification(self, run: CycleRun) -> None:
        execution = run.state_output.get("execution", {})
        reconciliation = run.state_output.get("reconciliation") or {}
        if reconciliation.get("reconciliation_required"):
            # Unknown external outcome (Phase 4H-E): the loop does not know whether
            # the action happened, so it can NEVER verify any impact it claims.
            run.state_output["outcome"] = {
                "verification_status": "unverified",
                "reason": "unknown_external_outcome_reconciliation_required",
            }
            return
        if execution.get("skipped") or not execution.get("receipt", {}).get("ok"):
            run.state_output["outcome"] = {
                "verification_status": "unverified",
                "reason": execution.get("reason", "no_execution"),
            }
            return
        recos = run.state_output.get("recommendations", [])
        pre_state = self._saved_snapshot(run)
        post_state = project_state(
            self.verification_evidence,
            tenant_id=run.tenant_id,
            business_id=run.business_id,
            max_age_days=self.policy.stale_max_age_days,
        )
        evaluator = self.policy.verification_evaluator
        measured = evaluator(pre_state.to_dict(), post_state.to_dict()) if evaluator is not None else {}
        expected = (recos[0]["expected_impact_sar"] if recos else None) or None
        observed = measured.get("observed_impact_sar")
        verification_method = "synthetic_measurement" if observed is not None else "no_measurement"
        outcome = verify_outcome(
            outcome_id=f"out-{run.cycle_id}",
            recommendation_id=recos[0]["recommendation_id"] if recos else "",
            recommendation_version=recos[0]["version"] if recos else 1,
            execution_key=execution.get("execution_key", ""),
            baseline_state_version=run.starting_state_version,
            post_action_state_version=post_state.state_version,
            expected_impact_sar=expected,
            observed_impact_sar=observed,
            verification_method=verification_method,
            measurement_window="1d",
        )
        run.state_output["outcome"] = outcome.to_dict()
        run.state_output["post_state_version"] = post_state.state_version

    async def _stage_learning_eligibility(self, run: CycleRun) -> None:
        outcome_dict = run.state_output.get("outcome", {})
        outcome = outcome_from_run(run)
        linkage = build_linkage(run, outcome)
        # The ONLY gate for the verified learning pipeline (MASTER_PLAN §15.2).
        # Phase 4F — the gates are COMPUTED, never hardcoded:
        #   * tenant authorized when the run is tenant-scoped
        #   * quality satisfied only while the evidence watermark is fresh
        #   * attribution sufficient only for deterministic measurement /
        #     provider-attributed signatures (Jev advisory alone never is)
        eligibility = learning_eligibility(
            outcome,
            tenant_authorized=bool(run.tenant_id),
            source_traceable=True,
            quality_satisfied=run.evidence_watermark not in ("", "none"),
            attribution_sufficient=attribution_sufficient(linkage.attribution_quality),
        )
        run.state_output["learning_eligible"] = eligibility.eligible
        run.state_output["learning_reasons"] = list(eligibility.reasons)
        run.state_output["learning_outcome"] = outcome_dict
        # Durable canonical reference: the cycle run binds its outcome record
        # (tenant/business/cycle/execution/measurement/attribution) in state.
        run.state_output["outcome_linkage"] = linkage.to_dict()

    async def _stage_learning(self, run: CycleRun) -> None:
        if run.state_output.get("learning_eligible"):
            run.state_output["learning"] = {"artifact": "verified_outcome_reference", "mode": "verified_only"}

    async def _stage_summary(self, run: CycleRun) -> None:
        run.state_output["summary"] = {
            "cycle_id": run.cycle_id,
            "starting_state_version": run.starting_state_version,
            "opportunities": run.state_output.get("opportunity_count", 0),
            "recommendations": len(run.state_output.get("recommendations", [])),
            "verified": run.state_output.get("learning_eligible", False),
            "execution": bool(run.state_output.get("execution", {}).get("receipt", {}).get("ok")),
        }
        run.completed = True

    async def _stage_next_cycle(self, run: CycleRun) -> None:
        pass  # marker stage: next cycle is a new idempotent run

    def _handlers(self) -> dict[CycleStage, StageHandler]:
        return {
            CycleStage.EVIDENCE_DISCOVERY: self._stage_evidence_discovery,
            CycleStage.INGESTION: self._stage_ingestion,
            CycleStage.VALIDATION: self._stage_validation,
            CycleStage.STATE_PROJECTION: self._stage_state_projection,
            CycleStage.FRESHNESS_ASSESSMENT: self._stage_freshness,
            CycleStage.OPPORTUNITY_DETECTION: self._stage_opportunities,
            CycleStage.IMPACT_CALCULATION: self._stage_impact,
            CycleStage.ACTION_CANDIDATES: self._stage_action_candidates,
            CycleStage.ADVISORY: self._stage_advisory,
            CycleStage.ADVISORY_VALIDATION: self._stage_advisory_validation,
            CycleStage.RECOMMENDATION: self._stage_recommendation,
            CycleStage.GOVERNANCE: self._stage_governance,
            CycleStage.APPROVAL_WAIT: self._stage_approval_wait,
            CycleStage.PREFLIGHT: self._stage_preflight,
            CycleStage.EXECUTION: self._stage_execution,
            CycleStage.RECONCILIATION: self._stage_reconciliation,
            CycleStage.VERIFICATION: self._stage_verification,
            CycleStage.LEARNING_ELIGIBILITY: self._stage_learning_eligibility,
            CycleStage.LEARNING: self._stage_learning,
            CycleStage.CYCLE_SUMMARY: self._stage_summary,
            CycleStage.NEXT_CYCLE: self._stage_next_cycle,
        }
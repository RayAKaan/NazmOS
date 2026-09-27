# PHASE 4G — Business Loop Command Center (tenant-scoped, read-only console)

**Status: PARTIAL ACCEPTANCE [V] (DB-free + frontend evidence committed; Postgres-backed
suites written, staged, and PENDING-PG in this environment).** The 4G console is a pure,
read-only projection over persisted loop state (`cycle_runs.state_output`) and the
EXISTING V1 `OutcomeLedger` — no new authority, no second store, no mutation verbs. It
answers "what did my own loop actually do, and was any of it verified/learned?" with
exact tenant scoping and DLP-clean payloads. The 3K source-string contract
(`tests/test_loop_console.py`) and the 4F outcome-linkage suite stay green. Evidence for
the Postgres-backed half (API boundary + the extended IDOR suite) is staged but could not
be executed here because no Postgres is reachable (no Docker daemon, no local service)
— see Blocked.

## Result (TL;DR)

`cycle_runs` rows now project into a frozen read model (`READ_MODEL_VERSION="1.0"`) and
are read out through three read-only routers under `/api/v1/loop-console`:

- `GET /cycles?business_id=` — paginated ladder (learning_eligible › verified › measured ›
  executed › blocked › running › not_run), lifecycle + execution + outcome + flags, and the
  impact expressed as a BAND (list views never leak exact SAR).
- `GET /cycles/{cycle_id}?business_id=` — owner-gated detail: exact observed/potential
  impact for the owner's own run, `impact_delta_sar` only when expected is known, stage
  timeline (21), recovery, verification/learning sections, and the persisted
  `outcome_key` via `outcome_linkage`/`outcome_recorded`.
- `GET /outcomes/verified?business_id=` and `GET /summary?business_id=` — the EXISTING
  V1 `OutcomeLedger` read through fail-closed tenant scoping (`verified` rows only;
  `configured=False` when `AI_OUTCOME_LEDGER_PATH` is unset).

The read model is derived from composed run state ONLY (verification/measurement/
learning/recovery/linkage are all recomputed deterministically); the console cannot
invent, upgrade, or re-author anything, and there is no execution/approval/rejection/
retry/resume path attached anywhere in the console. Authorization derives from the
principal (identity → `assert_business_access`), never from a caller-supplied
`business_id`; a foreign business is refused with 403 and an owner's unknown
`cycle_id` returns 404 (no scramble, no data). No schema change was required.

## Deliverables

| Artifact | Source | Evidence |
|---|---|---|
| `loop_console_readmodel.py` (new) — `READ_MODEL_VERSION=1.0`, `compute_lifecycle` ladder, `build_cycle_summary` (banded), `build_cycle_read_model` (detail) | `backend/app/services/` | new DB-free suite (17), Section A |
| `cycle_run_repository.py` — `_updated_at` private attr, `page()` (bounded, deterministic sort), `outcome_keys()` (scan `outcome_attachment`/`outcome_recorded`) | `backend/app/services/` | new suite Sections A–B |
| `/api/v1/loop-console` router (new) — three read-only verbs, `_scoped_verified_rows` fail-closed, `assert_business_access` | `backend/app/routers/loop_console.py` | string-contract `test_loop_console.py` + new suite |
| `tests/test_phase4_loop_console.py` (new) — Section A DB-free (lifecycle ladder, read-model purity + `cycle_id`, DLP/banned-substring, no-mutation-router, ledger scoping), Section B Postgres (repo `outcome_keys`, API 200/403/404) | `backend` | 17 passed, 6 skipped (PG) |
| `tests/security/test_idor_cross_tenant.py` (extended) — READ_CASES + POSITIVE_CONTROL `loop_console_cycles`, standalone detail-idor + unknown-id-404 | `backend` | py_compile clean; run PENDING-PG |
| `/loop` frontend page (new, read-only) | `frontend/src/app/(dashboard)/loop/page.tsx` | tsc clean, eslint 0 errors |
| middleware `"loop"` segment + matcher, Sidebar + MobileNav entries (each with `Activity` icon) | `frontend/src/middleware.ts`, `components/layout/Sidebar.tsx`, `MobileNav.tsx` | eslint 0 errors |
| `src/middleware.test.ts` +2 loops (authenticated `/loop` → 200; unauthenticated → 307 `/login`) | `frontend/src/middleware.test.ts` | jest 7/7 passed |
| `PHASE_4G_REPORT.md` + `MIGRATION_MATRIX.md` §11 4G row | repo root | — |

## The read model (as implemented)

```
cycle_runs.state_output (persisted run snapshot)
  ├─ compute_lifecycle          → 7-step ladder (blocked orthogonal; verified-first)
  │                                learning_eligible › verified › measured › executed ›
  │                                blocked › running › not_run
  ├─ build_cycle_summary        → list row: impact_band (never exact SAR), flags,
  │                                stage_index/stage_count, execution/outcome booleans
  └─ build_cycle_read_model     → owner detail: exact observed + potential impact,
                                impact_delta_sar (only when expected known), stage
                                timeline (21), recovery (execution_authority), links
                                (outcome_key from outcome_linkage/outcome_recorded)

OutcomeLedger V1 (unmodified)   → _scoped_verified_rows: verified=1 rows only, row
                                partition coerced to the caller's tenant → untrue
                                row-keys can never satisfy the scope check
```

`page()` is bounded `limit ∈ [1,100]`, `offset ≥ 0`, sort `created_at DESC, cycle_id ASC`
(deterministic, no ties → no N+1). Detail is resolve-able by key for the owner and
refuses cross-tenant reads. The ledger scope path is the only live read of V1 from the
console and it is fail-closed (all math identical to `verified_outcomes`; 0-config is
`configured=False`, never a fabricated 0).

## Verdict model

- **DLP**: list rows band impact; detail exact-SAR is owner-only (same ownership
  semantics as Money Audit). Read model contains no `"sku"`, `.sku`, `"stock_count"`,
  `"business_name"`, `async def`, or `CREATE TABLE` (asserted by test).
- **Attribution truth (unchanged from 4F)**: `attribution_quality` =
  `deterministic_measurement` for verified+measured runs; otherwise advisory provenance
  recorded verbatim (`mocked` stays `mocked`, never `jev`). Expected impact stays `None`
  when the rule is not supportable from the snapshot (e.g. transfer/reorder) — the console
  reports `impact_delta_sar=None`, never synthesizes a delta.
- **Authority**: the console composes persisted state; it never calls
  advisory/approval/execution/verification/mark-eligible surfaces to populate itself, and
  exposes no mutation endpoint (asserted by substring scan of the router module).

## Evidence

```
# 4G DB-free suite (Section A) + Postgres-gated (Section B)
$env:PYTHONPATH="H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED\backend"
$env:USE_TEMPORAL="false"
$env:DATABASE_URL="postgresql+asyncpg://nazmos:nazmos_v5_dev@localhost:5432/nazmos_test"
$env:TEST_DATABASE_URL="postgresql+asyncpg://nazmos:nazmos_v5_dev@localhost:5432/nazmos_test"
python -m pytest tests/test_phase4_loop_console.py -q
=> 17 passed, 6 skipped (skips = Section B, Postgres-gated: repo boundary + API auth)

# aggregate gate: 4G + 3K string-contract + 4F linkage
python -m pytest tests/test_phase4_loop_console.py tests/test_loop_console.py \
  tests/test_phase4_outcome_linkage.py -q
=> 54 passed, 6 skipped (10.26s)

# prior full non-temporal regression (7 files incl. new suite + existing loop/console/repo)
=> 82 passed, 13 skipped (74.41s), all skips Postgres-gated

# security suite (aggregate)
python -m pytest tests/security -q
=> 189 passed, 31 skipped, 7 errors (all 7 = test_celery_rls_tenant_context.py
   ConnectionRefusedError — requires live Postgres synchronously; environmental,
   unrelated to 4G)

python -m compileall -q app tests alembic   (backend)
=> COMPILE_EXIT=0

# frontend
npx tsc --noEmit                                   => clean
npm run lint                                         => 0 errors (6 pre-existing
   window.location.href warnings in untouched files)
npx jest src/middleware.test.ts                      => 7 passed (5 existing + 2 new /loop)
npx eslint <5 changed files>                         => clean
```

## IDOR extension (written; execution PENDING-PG)

`tests/security/test_idor_cross_tenant.py` now reads:
- READ_CASES += `loop_console_cycles` (`GET /api/v1/loop-console/cycles`) on top of the
  pre-existing `loop_console_policy` / `loop_console_verified_outcomes` /
  `loop_console_summary` cases.
- POSITIVE_CONTROL_CASES += `loop_console_cycles`.
- Standalone `test_attacker_cannot_read_victim_loop_cycle_detail` (two args — path
  `cycle_id` + query `business_id` — which the parametrized harness cannot express) and
  `test_owner_unknown_loop_cycle_id_is_404_not_data`.

These, with `tests/phase4/` IDOR and the API Section B, run as soon as a Postgres is
reachable (exact command in the Acceptance run below).

## Acceptance checklist (4G master directive)

- [V] read-only console: composite of persisted run state (no mutation verbs, no refresh
  authority; `GET` only)
- [V] tenant scoping: `assert_business_access` on the principal; cross-tenant 403; owner
  unknown `cycle_id` → 404 without data
- [V] DLP-clean: exact-SAR confined to owner detail + contextualized banded list; SKUs /
  payloads / chain-of-thought never rendered (read model is identifier + metric only)
- [V] no new schema: `cycle_runs.state_output` + V1 ledger only; `_updated_at` exists
  solely for UI fidelity on rehydrated runs
- [V] bounded pagination + deterministic sort (no N+1)
- [V] verified-outcome read is the existing V1 ledger, fail-closed, 0-config honest
  (`configured=False`, rows exactly `verified=1`)
- [V] no second ledger / store / authority; `outcome_ledger` substring + no
  `OutputLedger` text preserved in the router
- [~] Postgres-backed API boundary (Section B) + IDOR evidence — staged, PENDING-PG
- [V] frontend: `/loop` page composes the three read endpoints owner-gated, badges
  revalidation/execution honestly, renders reason column; middleware auth for `/loop/*`;
  nav entries present; jest 7/7, tsc clean, eslint 0 errors

## Notes / limitations

- **[X] Postgres unavailable in this working environment** (`Test-NetConnection
  localhost:5432` → False; Docker Desktop not running; no local service). Consequences,
  all evidence-staged rather than evidence-blocked: Section B (6), the IDOR extension,
  and the 7 pre-existing celery RLS connection errors cannot execute here. The suites are
  written, compiled, and reviewed; run them against any migrated PG to close the loop.
- **[X] Ledger stays opt-in** (`AI_OUTCOME_LEDGER_PATH`, default `""`) — consistent with
  4F; linkage data is durable in `state_output` regardless.
- **No migrations**: 4G is a read projection over existing tables; the console added no
  column, table, index, or RLS change.
- **No commits/pushes; no infra changes; no destructive operations.**
- **[X] Pre-existing baseline breakage** (`sqlite_db` fixture undefined for the two n2
  probe real-emission tests) remains out of 4G scope — flagged per prior phases.

## Next (4H/4I)

4H hardening: concurrent-duplicate lock / reconcile on the same cycle; 4I crash-resume
acceptance. Prior to accepting 4G fully, close the PENDING-PG item (below) so Section B +
IDOR evidence is complete.

## Acceptance run (when a Postgres is reachable)

```bash
cd backend
$env:PYTHONPATH="H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED\backend"
$env:USE_TEMPORAL="false"
$env:DATABASE_URL="postgresql+asyncpg://nazmos:nazmos_v5_dev@localhost:5432/nazmos_test"
$env:TEST_DATABASE_URL="postgresql+asyncpg://nazmos:nazmos_v5_dev@localhost:5432/nazmos_test"
python -m pytest tests/test_phase4_loop_console.py -q                # expect 23 passed
python -m pytest tests/security/test_idor_cross_tenant.py -q         # IDOR incl. 4G cases
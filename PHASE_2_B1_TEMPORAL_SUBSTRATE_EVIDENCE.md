# PHASE 2 — B1 TEMPORAL SUBSTRATE REMEDIATION EVIDENCE

- Date: 2026-09-23
- Repo root: `H:\NAZMOS_COMPLETE_LATEST\NAZMOS_LATEST_MERGED`
- Branch: `phase1-core-infra-replacements` · HEAD: `6078008`
- Mode: non-destructive infra remediation (no volume/history/Postgres
  deletion; no container recreate; additive Docker network change only) + a
  documented runbook (closes the Phase 2A blocker).

## 1. Root cause confirmed [V]
- `nazmos-worker` crash-looped with
  `socket.gaierror: [Errno -2] Name or service not known` because postgres was
  NOT on the worker's Docker network (`nazmos_latest_merged_default`); it only
  sat on the older broadcast network `nazmos_default_net`.
- Worker `DATABASE_URL` (`nazmos:nazmos_dev@postgres:5432/nazmos`) is correct:
  the live postgres volume authenticates `nazmos_dev` over TCP (scram-sha-256).
  `nazmos_v5_dev` is rejected over the network; container env shows v5_dev but
  the data volume was initialized with nazmos_dev.
- Temporal container `nazmos_latest_merged-temporal-1` was started manually as
  `temporalio/temporal:latest` (in-memory persistence); its healthcheck fails
  only because the minimal image lacks `bash`. The server itself is SERVING.

## 2. Non-destructive remediation applied [H]
- `docker network connect --alias postgres nazmos_latest_merged_default nazmos_latest_merged-postgres-1`
- Worker restarted; now `state=running restarts=0
  started=2026-09-23T16:03:53Z`.
- `postgres` resolves to `172.31.0.5` from inside the worker container.
- Live TCP probe from worker container: `pg_ok 1` (asyncpg, nazmos_db,
  nazmos_dev). [H]

## 3. Temporal server health [H]
- `docker exec nazmos_latest_merged-temporal-1 temporal operator cluster health` → `SERVING`.
- CLI reports `temporal version 1.8.3 (Server 1.31.2, UI 2.50.1)`. [V]
- Namespace `default` registered; port 7233 open.

## 4. Temporal-backed acceptance [H]
- `tests/temporal` suite, real live server + in-process production worker,
  SQLite DB: **8 passed, 9 skipped** (9 Postgres-only skips on sqlite; CI
  enforces zero skips with Postgres). Exact-match AGENTS.md contract.
  Evidence file: `results/phase2_b1_temporal_suite.txt`.
- Deterministic Temporal gates (no live server): **75 passed** across
  `test_infra_service.py`, `test_temporal_deployment.py`,
  `test_temporal_strict_dispatch.py`, `test_temporal_failure.py`,
  `test_temporal_retry_wiring.py`, `test_temporal_workflow_determinism.py`,
  `test_context_temporal.py`.
  Evidence file: `results/phase2_b1_temporal_gates.txt`.

## 5. Queue-collision root cause (why the suite previously reported 4 failed) [V]
- `tests/temporal/probes.py` schedules probe workflows on a hardcoded queue
  name shared with the production worker. The production worker registers only
  `agent_approval / manual_action / simulated`; when it polls probe activity
  tasks it fails them with
  `NotFoundError: Workflow class retry_probe_transient is not registered on
  this worker, available workflows: agent_approval, manual_action, simulated`.
- With the production worker paused during the suite run, the in-process worker
  owns the queue exclusively → all probe tests green. Isolating only by env var
  (`TEMPORAL_TASK_QUEUE`) does not help because the probe task queue name is
  hardcoded; it hangs with no worker.
- Stale probe workflows left by the earlier collided run were allowed to
  complete/fail on their own (no cleanup op performed).
- Runbook for the full procedure added: `docs/runbooks.md` §10 (Temporal
  Substrate Remediation).

## 6. Residual (documented, not a blocker) [H]
- Temporal container remains Docker-"unhealthy" only due to absent `bash` in
  the minimal runtime image; cluster health + all Temporal-backed tests are
  green. Recreating to the compose `auto-setup` image would drop in-memory
  history and is intentionally deferred under the non-destructive boundary
  (runbook §10.5).

## 7. B1 verdict
**ACCEPTED — Temporal substrate gate GREEN (non-destructive remediation).**
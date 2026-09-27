# PHASE 4C — Jev-Native Typed Advisory via the Canonical Gateway

**Status: DONE [V]** — DB-free suite green, production wiring gap closed.

## Result (TL;DR)

The business loop's advisory now routes through the SAME canonical AI gateway
the controller/OpenCode surfaces use (`ai_gateway.systemone_reason`), and the
loop's advisory capability is registered in the AI policy anchor table — it was
silently policy-blocked in production before this phase. All invariants from
`PHASE_4A_RUNTIME_CONTRACT_REPORT.md` §5 hold under 11 new DB-free tests.

## Deliverables

| Artifact | Source | Evidence |
|---|---|---|
| `tests/test_phase4_jev_advisory.py` (new) | `backend` | 11/11 passed |
| `ai_policy.py` capability registration (fixed) | `app/security/ai_policy.py` | `business_loop.action_selection` now in `AI_CAPABILITIES` + `AI_CAPABILITY_FLAGS` |
| `PHASE_4C_REPORT.md` (this) | repo root | — |
| `MIGRATION_MATRIX.md` §11 row | repo root | 4C row `[V]` |

## Why this mattered (the production bug 4C caught)

`_stage_advisory` calls `consult_advisory(self._advisory_fn(), ...)` with
`capability="business_loop.action_selection"` (cycle.py:361). The canonical
gateway (`ai_gateway.systemone_reason`) is the only blessed AI entry point and
it evaluates `AiPolicy.allow_request()` FIRST. Before 4C, that capability was
**not** in `AI_CAPABILITIES`, so the policy fail-closed to
`AI_POLICY_BLOCKED` → every production loop advisory consult returned
`source == "fallback"`. Jev would never have been consulted. 4C surfaced this
with a failing test and closed it with a one-line registry addition
(deny-by-default semantics preserved — unknown capabilities still blocked).

## Contract proven (each maps to a 4A invariant)

1. **Typed advisory via canonical entry** — `canonical_advisor` →
   `systemone_reason` → `jev.consult` returns a normalized `TypedAdvisory` with
   `capability`, `deterministic_decision`, `suggested`, confidence, source,
   provider, and validation flags (test 1).
2. **Deterministic ALWAYS authoritative** — Jev disagreeing
   (`suggested=RESTOCK` vs deterministic `REORDER`) changes nothing on the
   decision (test 3). Agreement nullifies the redundant alternative (test 2).
3. **Exact attribution, mocked never jev** — `source=mocked` survives
   end-to-end; disabled Jev resolves to `DETERMINISTIC_ONLY` +
   `UNKNOWN_PROVIDER_SOURCE:fallback` (never claimed as Jev); the fail-closed
   `deterministic_only_advisor` never labels Jev (tests 4–6).
4. **Out-of-contract advisory dropped, never coerced** — `LAUNDER_MONEY`
   outside the contract → `suggested is None` + `OUT_OF_CONTRACT` +
   `validation_passed False` (test 7). Malicious/corrupt answers stay advisory
   (test 8).
5. **Capsule DLP-clean on the wire** — the stub transport records the exact
   outbound HTTP body; `state` equals `capsule.for_prompt()`: tenant id,
   business id, SKUs, product/supplier names, exact stock counts and exact SAR
   amounts are all absent; only opaque refs (`item_A`/`item_B`) + banded
   signals present; trusted-zone bookkeeping (`capsule_id`, `request_id`,
   `nonce`, `signature`, `capsule_hash`) never leaves (tests 9–10).
6. **Signed-capsule invariant** — `jev.consult()` refuses a raw dict with a
   `TypeError`; the gateway builds a verifiable signed capsule (test 11).

## Evidence

```
$env:PYTHONPATH="...\backend"
$env:USE_TEMPORAL="false"
python -m pytest tests/test_phase4_jev_advisory.py -q
=> 11 passed

# regression (post ai_policy change)
python -m pytest tests/test_business_loop_modules.py tests/test_canonical_controller.py \
  tests/test_phase3_synthetic_vertical_slice.py tests/phase4 \
  tests/test_cycle_run_repository.py -q
=> 64 passed
TESTS_DATABASE_URL=postgresql+asyncpg://nazmos:nazmos_v5_dev@localhost:5432/nazmos_test
python -m pytest tests/security/test_idor_cross_tenant.py -q   # DB env required
=> 26 passed
python -m compileall -q app tests  => OK
```

## Notes / limitations

- **[X] Live Jev credentials were absent** — all Jev interaction used the
  `JevClient(transport=MockTransport)` pattern from
  `test_canonical_controller.py`; the transport records the real outbound JSON
  so the DLP assertion is against the actual wire shape, but no real provider
  round-trip was exercised.
- **[X] `ai_policy.py` registration is production-relevant** — the loop
  advisory consult now passes the policy gate. The capability purpose string
  doubles as the declared purpose (must contain `continuous_business_loop`,
  which `_stage_advisory` passes); kept in sync.
- **No new tables, no migration, no infra changes** — 4C is DB-free by design
  (4A §5). Postgres var needed only for the DB-backed regression suites.
- **No commits/pushes made.**

## Next (4D)

Start `temporal-1` container only; prove the in-process production
`build_worker` path first (post payload typed-advisory + durable dispatch +
recovery/reconcile), then `docker start nazmos_latest_merged-nazmos-worker-1`
(Option 2: no recreate/rebuild).
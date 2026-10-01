# Phase 1 Audit — Universal Business Reality

Audit of the NazmOS repository before implementing Phase 1. Every claim below was
verified by reading code, not inferred from documentation. Historical phase
documents are treated as non-authoritative per the specification.

**Audit date:** 2026-10-01
**Baseline commit:** `3e79e08` (`chore: finish repository root cleanup`, `main`)
**Baseline test result:** 1505 passed, 2 failed (pre-existing), 8 skipped, 1 xfailed

---

## 1. Headline finding

**Orbit is designed and migrated but entirely unwired.**

| Symbol | Callers |
|---|---|
| `run_orbit_financial_xray()` | 1 — an unused import at `app/services/audit_persistence.py:15` |
| `AuditPersistenceService.save_audit_run()` | **0** |
| `orbit_file_manifest` / `orbit_data_quality` writes | **0** |

Consequences:

- `app/routers/orbit.py` is registered (`app/main.py:207`) but reads
  `orbit_audit_runs`, `orbit_evidence`, `orbit_data_quality` — tables that never
  receive a row.
- Nothing in the ingestion path builds an `OrbitAuditResult`, so the canonical
  analysis output is never produced.
- Phase 1's job is therefore substantially **wiring**, not extension.

---

## 2. Audit results by area

### 2.1 Ingestion — 7 competing paths

| # | Path | Entry | Produces |
|---|---|---|---|
| 1 | Authenticated upload → ETL | `routers/upload.py:64` → `tasks/ingestion_tasks.py:54` → `services/etl_pipeline.py` | ad-hoc rows → `items`/`inventory`/`transactions` |
| 2 | Authenticated JSON | `routers/upload.py:527` | same ETL, skipping validation + mappers |
| 3 | Guest single-file | `routers/guest_audit.py:109` | `BusinessSnapshot` (in-memory only) |
| 4 | Guest two-file | `routers/guest_audit.py:206` | `BusinessSnapshot` (in-memory only) |
| 5 | Guest multi-file | `routers/guest_audit.py:138` | **broken** — see below |
| 6 | Guest JSON | `routers/guest_audit.py:265` | `BusinessSnapshot` (in-memory only) |
| 7 | POS webhooks | `routers/pos_webhooks.py` → `adapters/foodics.py`, `adapters/salla.py` | raw SQL inserts; bypasses Orbit entirely |

Plus `ETLPipeline.process()` (`etl_pipeline.py:49`) — a self-described legacy API
with zero callers.

**Paths 1–2 never construct a `BusinessSnapshot`.** Paths 3–6 build one but never
persist it and never run the X-Ray. So no path produces canonical reality.

**Path 5 is dead code.** `guest_audit.py:150` calls `uuid4()` but line 16 imports
only `import uuid`, so the route raises `NameError`.

### 2.2 File loaders — 3, with different format support

| Loader | Location | Formats |
|---|---|---|
| `load_workbook` | `services/workbook_loader.py:376` | csv, xlsx, xlsm, xls, json |
| `parse_file_with_report` | `services/upload_service.py:16` | csv, xlsx, xls — **raises on json** |
| `process_upload` | `services/upload_service.py:66` | dead wrapper |

### 2.3 Column mappers — 4, disjoint output namespaces

| Mapper | Location | Vocabulary | Output roles |
|---|---|---|---|
| `resolve_columns` | `services/file_ingestion.py:337` | ~120 EN/AR aliases | 6 ledger roles |
| `infer_schema` | `services/semantic_mapping.py:534` | weighted token table | 20 canonical roles |
| `SchemaDetector.detect` | `services/schema_detector.py:176` | finite name hints + Levenshtein | 23 target roles |
| inline dict | `services/etl_pipeline.py:49` | hardcoded | 6 roles |

The strongest mapper (`semantic_mapping`) is used only on the guest path; the two
highest-trust authenticated paths use the weakest one.

### 2.4 Document extraction — absent

No `pdfplumber`, `pypdf`, `PyPDF2`, `python-docx`, `pytesseract`, `PyMuPDF`, or
`Pillow` anywhere in `backend/` or `backend/requirements.txt`. Upload allowlists
(`services/file_validator.py:7`, `app/config.py:158`, `routers/guest_audit.py:36`)
reject PDF/DOCX/image outright.

### 2.5 Entity resolution — 5 independent implementations, no shared service

`product_pairing.pair_products` (rapidfuzz, `product_pairing.py:62`),
`schema_detector._levenshtein_similarity` (header matching only),
`adapters/item_resolver.resolve_item` (4-tier SQL, tier 4 is a 10-char substring),
`supplier_price_ingestion._get_or_create_supplier` (unanchored `ILIKE '%name%'`),
`recovery_match_service._compute_match_score` (cross-business heuristic).

`etl_pipeline._upsert_items` uses exact-only matching, so `"Almarai Milk 1L"` and
`"Almarai Milk"` become two items.

No customer or employee resolution exists.

### 2.6 Time normalization — 5 parsers, conflicting ambiguity resolution

| Parser | `03/04/2026` resolves to |
|---|---|
| `data_normalizer.parse_date` (ETL paths 1–2) | **3 April** (`DATE_FORMATS[1] = %d/%m/%Y`) |
| `business_snapshot_builder._parse_date` (guest 3,4,5,6) | **4 March** (no `dayfirst`) |
| `guest_audit_service._parse_date` (guest 3,6) | **4 March** |

`ingestion_schema.ERROR_CODE_AMBIGUOUS_DATE_FORMAT` is declared at
`ingestion_schema.py:103` and **never emitted**.

### 2.7 Unit / currency normalization — absent

`items.unit` is hardcoded `'piece'` (`etl_pipeline.py:363`); `pack_size` is
free-text passthrough (`models.py:304`). No conversion layer exists.

`file_ingestion.py:234` and `column_profiling.py:101` strip **both** `SAR` and
`USD` and return a bare number, discarding the currency. A USD file is therefore
silently labelled SAR. No FX table, rate or `exchange_rate` column exists.

### 2.8 Evidence / provenance — broken and unaddressed

- `orbit_evidence.finding_id` and `.metric_name` are **always empty**:
  `audit_persistence.py:180-181` reads keys that `EvidenceRecord.to_dict()`
  (`orbit_domains/evidence.py:42-49`) never emits.
- Five incompatible `evidence_id` schemes: risk-derived string, `uuid4` hex,
  checksum digest, transaction `row_hash`, file sha256.
- **`content_hash` does not exist** anywhere in the repository — there is no
  content-addressed idempotency anchor.
- `orbit_domains/evidence.py:29` — `EvidenceRegistry.add()` silently overwrites
  on duplicate id (last-write-wins), so it is not append-only.
- `app/services/evidence_package.py` is a *second, parallel* evidence contract
  carrying `sku`, `product_name` and exact SAR — the very fields the AI privacy
  boundary forbids sending to Jev.

### 2.9 Conflict detection — absent

- `business_snapshot_builder._add_inventory_data:159-161`:
  `if cost > 0 and entry.cost == 0: entry.cost = cost` — first non-zero wins
  silently, no record of the prior value or its source.
- `business_snapshot_builder._add_inventory_data:138-165` assigns
  `entry.stock` with plain last-write-wins.
- `product_pairing` computes a `PairingReport` but `guest_audit_service.py:501-514`
  only reports counts; the snapshot merge uses exact-name joins and ignores it.
- `business_loop/evidence.py:163-178` has `mark_conflict()` / `apply_correction()`
  but they are in-memory, loop-internal and never called from ingestion.

### 2.10 Data quality — 4 competing implementations, none canonical

| Implementation | Location | Scale | Wired to Orbit |
|---|---|---|---|
| `_quality` | `money_audit_service.py:77` | 0–100 | no |
| reject-rate formula (duplicated twice) | `upload.py:148`, `etl_pipeline.py:162` | 0–100 | no |
| limitations coverage | `intelligence/context.py:239` | 0.0–1.0 | yes, but Orbit is never populated |
| `_score_data_quality` | `orbit_financial_xray.py:194` | **hardcoded 91** | hardcoded |
| `DataQualityModel` | `ingestion_schema.py:158` | — | **never instantiated** |
| `_audit_to_comparison_dict` | `audit_persistence.py:398` | **hardcoded 91** | — |

`DataQualityModel` is imported at `file_ingestion.py:26` and never used.

### 2.11 Orbit domain engines — stubbed

| Location | Stub |
|---|---|
| `orbit_financial_xray.py:175` | `return 62  # Placeholder` (inventory score) |
| `orbit_financial_xray.py:190` | `return 69  # Placeholder` (procurement score) |
| `orbit_financial_xray.py:194` | `return 91` (data quality) |
| `orbit_domains/health.py:61` | computes `data_quality_score`, then discards it in a `0.10` weight |
| `orbit_domains/health.py:66-70` | all `DomainScore.confidence` hardcoded |
| `orbit_domains/inventory.py:38-43` | `dead_stock_sar`, `slow_stock_sar`, `overstock_sar`, `stockout_risk_sar`, `capital_trapped_sar` all `0.0` |
| `orbit_domains/margin.py:41-46` | `gross_margin_pct=0.0`, `cost_inflation_pct=0.0`, `margin_contribution={}` |
| `orbit_domains/sales.py:56-59` | `declining=[]`, `volatility=0.0`, `branch_contribution={}` |
| `orbit_domains/procurement.py:30-36`, `expense.py:26-39` | all zero/empty |
| `orbit_domains/cafe.py` | `CAFE_CONFIG` never consumed |

### 2.12 Orbit engine — triplicated methods (dead code)

| Method | Defined at |
|---|---|
| `_build_evidence_registry` | `:401`, `:505`, `:600` |
| `_build_limitations` | `:444`, `:543`, `:638` |
| `_collect_all_metrics` | `:472`, `:567` |

Python keeps only the last definition, so roughly 165 lines
(`:401-503`, `:505-565`) are unreachable. `run()` also calls
`_generate_opportunities`, `_build_evidence_registry` and `_build_limitations`
twice each (`:82-88` and `:105-107`) and builds the domain analyzers twice
(`:50-54` and `:64-68`). `cafe_config` is computed at `:56` and never used.

### 2.13 LLM reachability from Orbit — none

Verified by AST import-graph closure over both module-level and deferred imports:

| Entry point | Module-level closure | Including function bodies |
|---|---|---|
| `orbit_financial_xray` | no LLM | no LLM |
| `orbit_contracts` | no LLM (stdlib only) | no LLM |
| `orbit_domains` | no LLM | no LLM |
| `file_ingestion` | no LLM | no LLM |
| `ingestion_tasks` | no LLM | no LLM |
| `routers/upload` | no LLM | reaches `ai_gateway` → `jev` only |

`orbit_contracts.py:9-16` imports only `dataclasses`, `datetime`, `decimal`,
`typing`, `uuid`. No `openai` / `anthropic` / `google.generativeai` package is
imported anywhere in `backend/`.

The single deferred path (`upload.py:243` → `orchestration/operations.py:162` →
`business_loop/cycle.py:26` → `business_loop/advisory.py:152`) is inert: it
dispatches `OP_UPLOAD_INGEST`, which never constructs a `CycleOrchestrator`, and
the production advisor is the synthetic one.

### 2.14 LLM modules that ARE active (outside Orbit)

| Module | Provider | Reached from |
|---|---|---|
| `llm_orchestrator.py` | Groq, Google Gemini (`:16-17`) | `routers/money_audit.py:656` ab-compare, `routers/chat.py:165` |
| `llm_rate_limiter.py` | — | `routers/ops.py:13`, chat, money_audit |

These are Phase 2 concerns and must stay out of Phase 1.

### 2.15 OpenCode — already removed from the active architecture

- `backend/opencode_runner/agents/nazmos-brain.md` (657 lines) has **zero runtime
  readers**.
- No `opencode` service in any compose file; no `COPY` in any Dockerfile.
- `backend/tests/regression/test_adversarial_matrix.py:127`
  (`test_agent_file_is_never_self_modifying`) asserts the string `nazmos-brain.md`
  appears in `app/security/ai_adapter.py`. It does not — **this test fails today**.
- Remaining references are doc-only, test-only, migration-history prose, or a
  `.gitignore` entry.
- `app/services/opencode_brain.py`, `app/security/master_prompt.py` and
  `backend/opencode_runner/server.mjs` no longer exist.

### 2.16 Jev — a sound foundation to build on

`app/services/ai_providers/jev.py` import closure is exactly 3 modules
(`app.config`, `app.security.capsule`, `httpx`). It is a self-contained HTTPS
provider with:

- retry on `429/500/502/503/529`, 3 attempts, linear backoff (`:39-41`)
- hard type gate rejecting non-`ReasoningCapsule` input (`:206-210`)
- `decision_basis` always set to the caller's deterministic decision (`:44-60`)
- out-of-contract suggestion rejection (`:266-285`)
- fail-closed `source="fallback"` on every error path

`app/services/canonical_controller.canonical_decision()` (`:254-337`) is already
the deterministic-first, verify-then-finalize, contract-bounded primitive Phase 1
needs. **Reuse it rather than inventing a second judgment path.**

Two defects to fix:

1. **Capsule hash mismatch.** `canonical_controller.py:275` builds capsule #1, then
   `ai_gateway.systemone_reason` builds capsule #2 from identical arguments
   (`ai_gateway.py:107`). Jev receives #2, but `_record_shadow` and
   `_capture_outcome_ledger` persist #1's `capsule_hash`. The audited fingerprint is
   not the one that crossed the wire.
2. **`intelligence.recommendation_advisory` is unregistered.**
   `app/security/ai_policy.py:18-32` denies by default, so that capability is
   permanently policy-blocked. Phase 2 concern; reported, not fixed here.

### 2.17 Jev capability slots already taken

`AI_CAPABILITIES` (`ai_policy.py:18-32`) holds 13 entries. Eight are wired to
`canonical_controller` surface helpers — **all of which have zero production
callers**. `procurement.supplier_risk` is registered with no surface.
`counterfactual_audit`, `challenge` and `chat` route to Groq/Gemini, not Jev.

A Phase 1 capability registry must not collide with these names.

### 2.18 Jev audit sinks

Four sinks, inconsistent:

| Sink | Location | Notes |
|---|---|---|
| `ai_reasoning_requests` | Postgres | `status` hardcoded `"completed"`; no suggestion/confidence/latency stored |
| `security_events` | Postgres | `_scrub_detail` allowlist silently drops `jev_suggested` |
| `outcome_ledger_v1` | SQLite file | only when `AI_OUTCOME_LEDGER_PATH` is set (default `""`); `model` hardcoded `"jev-1.13.0"` |
| `shadow_capture.py` | JSONL | best-effort, swallows all exceptions |

`JEV_SHADOW_ENABLED` (`config.py:19,149`) is **dead** — never read by `app/`.

### 2.19 Production boot requires an LLM key

`config.py:417-421` and `:442-446` hard-require `GROQ_API_KEY` or
`GOOGLE_AI_API_KEY` when `ENVIRONMENT=production`, mirrored in
`app/utils/startup_checks.py:48-53` and `scripts/check_env.py:66-67`. Phase 1 must
not inherit this: a business-reality layer must be able to boot with **no** LLM
credentials.

### 2.20 Fixtures, tests, ops

- Fixtures: **27 CSV + 26 PNG** across `tests/fixtures/` and `backend/tests/fixtures/`.
  **Zero XLSX, XLS, PDF, DOCX.**
- `backend/tests/seed.py` — demo seeder gated on `ALLOW_DEMO_SEED`.
- 167 test files. Ingestion/Orbit-adjacent: `test_etl_pipeline.py`,
  `test_etl_dedup.py`, `test_guest_audit.py`, `test_phase_c_file_ingestion.py`,
  `test_phase_c_product_pairing.py`, `test_phase_c_workbook_loader.py`,
  `test_semantic_ingestion.py`, `test_upload.py`, `test_upload_confirm_mapping.py`.
- Docker is in good shape: `docker-compose.local.yml` has a `migrate` service
  (`alembic upgrade head`) gated by `service_completed_successfully`; postgres,
  redis, temporal and api all have healthchecks.
- CI (`ci.yml`): `backend`, `temporal-backend`, `frontend`, `token-guard`,
  `security-scan`.
- Alembic head on `main`: `ff16_orbit_tables`.

---

## 3. Decisions

### Retained (reuse as-is)

| Component | Why |
|---|---|
| `orbit_contracts.py` (`BusinessSnapshot`, `OrbitAuditResult`, `MetricValue`, …) | The canonical shape is correct; Phase 1 produces it rather than re-inventing it. |
| `canonical_controller.canonical_decision` | Already deterministic-first, contract-bounded, audited, fail-closed. Phase 1 registers capabilities into it. |
| `ai_providers/jev.py` | LLM-free, 3-module closure, strong fail-closed ladder. |
| `privacy_firewall` / `capsule` / `ai_policy` | The privacy boundary already exists and is the only sanctioned route to Jev. |
| `etl_pipeline` projector methods | `_upsert_items`, `_apply_inventory_snapshot`, `_bulk_insert_transactions`, `_rebuild_summaries` write product tables correctly, including `row_hash` dedup. Kept as **projectors** of canonical state. |
| `file_validator` | Magic-MIME + `DANGEROUS_PATTERNS` + sha256 are sound input validation. |
| `workbook_loader` hardening | Zip-bomb cap, cell-length cap, external-link rejection, header dedupe, BOM/encoding handling. Ported into the unified loader. |
| `transactions` `row_hash` unique index | Already-correct transactional idempotency. |
| Docker compose + healthchecks + `migrate` service | Meets §56–58 already. |

### Extended

| Component | Change |
|---|---|
| `AuditPersistenceService` | Add artifact/evidence/entity/conflict/state persistence. `save_audit_run` gains a production caller. |
| `app/database/models.py` | Add Orbit ORM models (were migration-only DDL) + Phase 1 tables. |
| `orbit_financial_xray.py` | Replace every hardcoded score; delete the triplicated dead methods; remove the double-invocation of three helpers. |
| `orbit_domains/*` | Implement the zero-returning inventory/margin/procurement/expense/sales analyzers. |
| `ai_policy.AI_CAPABILITIES` | Register the 10 Phase 1 capabilities. |
| `canonical_controller` | Fix the capsule #1/#2 hash mismatch so the audited hash matches the wire. |

### Consolidated (single authority each)

| Concern | From | To |
|---|---|---|
| Ingestion | 7 paths, 3 loaders | one `orbit/ingestion/pipeline.py` + `loaders.py` |
| Column semantics | 4 mappers, 3 vocabularies | one `orbit/semantics/vocabulary.py` + `column_mapper.py` |
| Row normalization | 3 normalizers | one `column_mapper.py` producing semantic roles |
| Entity resolution | 5 implementations | one `orbit/entities.py` |
| Time parsing | 5 parsers with conflicting `dd/mm` handling | one `orbit/normalize/time.py` |
| Data quality | 4 competing scores | one `orbit/quality.py` |
| Evidence | 5 id schemes + a parallel AI evidence contract | one content-addressed `orbit/evidence.py` |
| Freshness | per-service ad-hoc | one `evaluate_freshness()` in contracts |
| Jev access | direct `ai_gateway` calls | one `app/services/jev/` facade |

### Deprecated (kept working, no new callers)

`file_ingestion.COLUMN_ALIASES`, `semantic_mapping.SEMANTIC_SIGNATURES`,
`schema_detector.FIELD_PATTERNS`, `data_normalizer.FIELD_TARGETS`,
`workbook_loader.resolve_columns`, `product_pairing.pair_products`,
`item_resolver.resolve_item`, `anomaly_detector` (already documented as
orphaned), `services/evidence_package.py` (parallel AI evidence contract),
`llm_orchestrator` (Phase 2), `ai_reasoning`, `ai_challenge` (Phase 2).

### Removed

| Item | Reason |
|---|---|
| `backend/opencode_runner/agents/nazmos-brain.md` | Zero runtime readers; Phase 1 forbids OpenCode. |
| `etl_pipeline.process()` | Self-described legacy; zero callers; fourth normalizer. |
| `ETLPipeline(df=..., column_mapping=...)` constructor | Replaced by canonical-state input. |
| `intelligence/context.py` `_as_mapping` band-aid | It existed only to paper over `_row_to_orbit_result` returning raw JSON dicts into dataclass-typed fields. Fixed at the source instead. |

---

## 4. Constraints this plan inherits

1. **Orbit analytics must be implemented, not stubbed** — otherwise canonical
   context ships placeholder numbers and the acceptance criteria are meaningless.
2. **`ETLPipeline` projector tests must keep passing** — they encode the product's
   dedup and upsert semantics.
3. **No LLM reachable from `orbit/`** — enforced by an AST import-graph test.
4. **Production must boot without any LLM key.**
5. **167 existing test files** must not regress beyond the 2 known pre-existing
   failures.
6. **Historical Alembic migrations must not be rewritten** — `ff16` lineage is
   preserved and extended by `ff17` instead.

---

## 5. Phase 1 limitations (recorded, not hidden)

| Item | Status |
|---|---|
| IMAGE / OCR extraction | Out of scope for this phase. No OCR dependency is added. Recorded as a genuine external limitation with a failing acceptance test. |
| XLS (legacy binary) | `xlrd` reads values but not formulas or structural metadata. Reduced structural fidelity is documented, not silently ignored. |
| `intelligence.recommendation_advisory` | Permanently policy-denied (unregistered capability). Phase 2 concern; reported rather than fixed here. |
| Pre-existing test failures | `test_adversarial_matrix::test_agent_file_is_never_self_modifying` (stale assertion about a deleted OpenCode transport) and `temporal/test_full_integration::test_at_execution_constraint_block_is_durable_and_recorded`. Not introduced by Phase 1. |
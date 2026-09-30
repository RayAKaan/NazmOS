# Agent Instructions — NazmOS

## Product architecture

NazmOS is one AI-native Business Operating System with three capability layers:

1. Orbit — ingestion, canonical business state, Financial X-Ray, evidence and history.
2. Intelligence — monitoring, root cause, recommendations, Owner Copilot and bounded Jev advisory.
3. Loop — governance, approval, execution, reconciliation, verification and verified-only learning.

Do not create parallel product architectures or duplicate authorities.

## Authority boundaries

- Deterministic business logic is authoritative.
- Jev is advisory only and must never authorize or execute an action.
- AI output must be validated against the contract of the capability that requested it.
- Business mutations must flow through the canonical orchestration/execution path.
- Never bypass authorization, tenant isolation, governance or reconciliation.
- Never treat potential or expected financial impact as recovered cash.
- Missing data is not zero; stale data is not current data.

## AI / privacy boundary

The canonical structured AI entry point is:

    deterministic candidate
        → canonical controller
        → AI Gateway / Jev
        → typed validation
        → deterministic result remains authoritative

AI-facing payloads must use the privacy firewall/capsule boundary.

Never send:
- raw merchant identifiers
- tenant/business IDs
- SKUs or product names
- exact SAR values
- exact stock counts
- credentials or secrets
- unapproved raw database records

Prompts and model outputs must pass the repository's DLP and validation controls.

## Execution boundary

All real execution must converge on the canonical orchestration layer under backend/app/orchestration/.

Do not add a new direct mutation path from routers, agents, LLM/Jev providers, services or background tasks.

Execution must be:

    Decision → Governance → Approval → Temporal → Execution Dispatcher
             → External System → Reconciliation → Outcome

A retry must reconcile external state before attempting a potentially duplicated mutation.

## Business Loop

The canonical improvement loop is:

    Evidence
    → Business State
    → Opportunity
    → Advisory
    → Recommendation
    → Governance
    → Approval
    → Execution
    → Reconciliation
    → Measurement
    → Verification
    → Learning Eligibility
    → Next Cycle

Only traceable, authorized, verified outcomes may enter learning.

## Orbit

Orbit is evidence-first and deterministic.

Canonical flow:

    Upload / integration
    → universal ingestion
    → semantic mapping
    → data-quality assessment
    → canonical Business Snapshot
    → Financial X-Ray
    → persisted audit/evidence
    → history

Do not reintroduce upload-specific analyzers that bypass the canonical snapshot.

## Code organization

- backend/app/analytics/ — raw analytical calculations.
- backend/app/routers/ — HTTP/API boundaries.
- backend/app/services/ — domain services and business logic.
- backend/app/orchestration/ — execution dispatch and Temporal workflows.
- backend/app/security/ — security, DLP, policy and tenant controls.
- backend/alembic/ — schema migrations.
- frontend/ — Next.js product UI.
- docs/ — documentation; do not add phase reports to repository root.
- scripts/ — current development/operational tooling only.

Historical experiments, obsolete phase harnesses and generated result dumps should not be reintroduced.

## Before changing code

1. Search for the existing implementation before creating a new one.
2. Identify the canonical authority for the behavior.
3. Check callers and tests.
4. Preserve tenant isolation and authorization.
5. Run focused tests.
6. Run the relevant full acceptance suite.
7. Remove obsolete code when a replacement becomes authoritative.

## Tests

Backend:

    cd backend
    python -m pytest -q
    python -m compileall -q app tests

Frontend:

    cd frontend
    npm run lint
    npx tsc --noEmit
    npm run build

For database/Temporal changes, use the repository's Postgres/Temporal acceptance environment.

## Documentation rule

Keep the repository root minimal:

- README.md
- AGENTS.md
- required project/configuration files

Product, engineering, research, strategy and historical documentation belongs under docs/.

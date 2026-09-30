# NazmOS

NazmOS is the AI-native Business Operating System by Nazmak.

> **See your business. Understand it. Improve it continuously.**

NazmOS turns fragmented business data into a continuously improving operating system for real-world businesses.

## Product architecture

NazmOS is one product with three capability layers:

**Orbit — See your business**
- Ingest sales, inventory, procurement, expenses and other business exports.
- Normalize inconsistent schemas and preserve data-quality evidence.
- Build a canonical Business Snapshot.
- Run the deterministic Financial X-Ray.
- Surface quantified exposures, findings, opportunities and evidence.

**Intelligence — Understand your business**
- Continuously monitor business state and change.
- Explain root causes from evidence rather than isolated metrics.
- Generate deterministic recommendations and priorities.
- Use Jev as a bounded, typed, non-authoritative advisory layer.
- Provide an Owner Copilot grounded in the business state.

**Loop — Improve your business**
- Govern decisions before execution.
- Require approval where policy requires it.
- Execute through the canonical orchestration path.
- Reconcile requested vs actual external state.
- Measure and verify outcomes.
- Feed only verified outcomes into learning.

The intended closed loop is:

```
SEE
  ↓
UNDERSTAND
  ↓
DECIDE
  ↓
GOVERN
  ↓
APPROVE
  ↓
EXECUTE
  ↓
RECONCILE
  ↓
MEASURE
  ↓
VERIFY
  ↓
LEARN
  ↺
```

## Repository structure

```
nazmos/
├── backend/                 # FastAPI application and domain logic
│   ├── app/
│   │   ├── analytics/       # Raw analytical calculations
│   │   ├── orchestration/   # Canonical execution and Temporal workflows
│   │   ├── routers/         # API surface
│   │   ├── security/        # Auth, tenant isolation, DLP, AI policy
│   │   └── services/        # Product/domain services
│   ├── alembic/             # Database migrations
│   └── tests/               # Backend tests
├── frontend/                # Next.js application
├── docs/                    # Current engineering/product documentation
│   ├── engineering/
│   ├── research/
│   ├── strategy/
│   └── archive/             # Historical reports retained only when useful
├── scripts/                 # Current development/operational tooling
├── sample_data/             # Current deterministic fixtures only
└── .github/                 # CI/CD
```

Historical phase reports and obsolete experiment harnesses are not part of the runtime codebase.

## Core technical principles

- **Deterministic business logic is authoritative.**
- **AI is advisory and contract-bound.**
- **Jev never directly mutates business state.**
- **Evidence is preserved for important findings and decisions.**
- **Missing data is not treated as zero.**
- **Potential financial impact is not presented as recovered cash.**
- **Execution has one canonical orchestration path.**
- **Retries reconcile external state before re-execution.**
- **Only verified, traceable outcomes are eligible for learning.**
- **Tenant isolation and authorization are enforced server-side.**

## Stack

### Backend
FastAPI, Python, SQLAlchemy, PostgreSQL, Alembic, Pydantic, Temporal, Redis where required, and typed Jev integration.

### Frontend
Next.js, React, TypeScript, Tailwind, Zustand, React Query and the Nazmak design system.

## Orbit data flow

```
Files / integrations
       ↓
Universal ingestion
       ↓
Semantic mapping + data quality
       ↓
Canonical Business Snapshot
       ↓
Deterministic Financial X-Ray
       ↓
Evidence + history
       ↓
Intelligence
       ↓
Business Loop
```

## Development

Backend:

```bash
cd backend
python -m pytest -q
python -m compileall -q app tests
```

Frontend:

```bash
cd frontend
npm ci
npm run lint
npx tsc --noEmit
npm run build
```

Use the repository's Docker/CI configuration for Postgres- and Temporal-backed acceptance tests.

## Documentation

- [Engineering documentation](docs/engineering/)
- [Research](docs/research/)
- [Strategy](docs/strategy/)
- [Operational documentation](docs/)
- [Historical archive](docs/archive/)

## Security

Read [AGENTS.md](AGENTS.md) before modifying AI, authentication, tenant isolation, orchestration, or execution code.

Never place secrets, raw merchant identifiers, exact financial values, or tenant-sensitive records into prompts or logs.

## Status

Orbit is the current product foundation. Intelligence is the next major capability layer, followed by production execution and learning in Loop.

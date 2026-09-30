# Repository Cleanup

Date: 2026-09-30

## Scope

Cleanup was performed against the main product repository before the Intelligence and Loop implementation.

## Removed

- Superseded OpenCode brain service and runner infrastructure.
- OpenCode-only security prompt/runtime components.
- Legacy V8/V9/V10/V11/V12 experiment harnesses and generated result sets.
- Test suites whose only purpose was deleted legacy services.
- Obsolete decision-value experiment code.
- Historical repository audit corpus that no longer describes the current implementation.
- Root-level historical phase reports and generated reports.
- Obsolete experiment datasets.

## Preserved

- Orbit ingestion, canonical snapshot and Financial X-Ray.
- Evidence, audit persistence and history.
- Live Money Audit and its current structured reasoning path.
- Canonical Jev gateway and typed controller contracts.
- Business Loop, governance, Temporal orchestration, reconciliation and learning infrastructure.
- Current security, tenant isolation and DLP controls.
- Current operational scripts required by CI/deployment.
- Current sample fixtures used by the product and tests.

## Documentation structure

The root is intentionally limited to repository entry-point files and required project configuration.

Documentation belongs under:

- docs/engineering/
- docs/research/
- docs/strategy/
- docs/

Historical material is not part of the active product architecture.

## Cleanup rule going forward

When a replacement becomes authoritative, remove the superseded implementation, its exclusive tests, and its generated artifacts in the same cleanup pass. Do not preserve parallel authorities merely for historical convenience.

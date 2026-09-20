# Terraform GCP path — retired (formerly `infrastructure/terraform/`)

## Decision (Production Reality Consolidation, Change 1)

The GCP Terraform path was a second, parallel target that was **never applied**:

- No `.tfstate*` files anywhere in the repository or listed infrastructure.
- No GCP credentials / service accounts referenced in the repository or in any
  CI workflow.
- `main.tf` builds a GCP VM + networking block that does not match the real
  deployments, which run as Docker Compose on managed VPS hosts
  (`staging.app.nazm.ai` / `app.nazm.ai`) reached over SSH by
  `.github/workflows/deploy.yml`.

Keeping two deployment worlds alive risks split-brain production. The VPS +
Docker Compose path is canonical and is the only one with evidence of having
been applied. This file is retained under `docs/archive/` as reference material
only. It is not part of the active deployment story and should not be revived
without a dedicated production-infrastructure decision.

Evidence of retirement is asserted in
`tests/test_production_reality.py` (no `infrastructure/terraform` tree,
deploy pipeline points at `docker-compose.prod.yml`).
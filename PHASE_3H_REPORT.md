# PHASE_3H — Execution & Reconciliation (`app/services/business_loop/execution.py`)

> Execution is dry-run/synthetic in the slice; reconciliation depends on the actual recorded state, never a blind retry. MASTER_PLAN §14, §19, §22.

## What was built

- **`ExecutionIntent`** — one idempotent intent; `execution_key` reuses `app/orchestration/keys.py::derive_execution_key` (SHA-256 hex over business+action+entity+payload+source). No parallel key derivation (`test_execution_key_is_deterministic` [V]).
- **`preflight`** — revalidates against `ACTION_REGISTRY`: unregistered → reject; `can_execute=False` → reject. No action executes without registry approval.
- **`dry_run_execute`** — only when governance = PERMITTED and recommendation = APPROVED. Returns a `SyntheticReceipt` with `synthetic=True` and note `SYNTHETIC - not a real merchant action` (asserted in the slice [V]). A dry-run is *never* represented as a real merchant action.
- **`reconcile`** — requested-vs-actual. `reported` (potentially succeeded) → **no blind retry** (`allow_retry=False`); `observed_no_effect` → retry eligible; failed/unconfirmed → never retried. (`test_reconciliation_no_blind_retry_when_reported` [V])

## Authority boundary

Execution passed `PERMITTED` **after** the approval gate already passed (registry + simulated owner approval in the slice). Nothing here re-authorizes; governance is the only gate.
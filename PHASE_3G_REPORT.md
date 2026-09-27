# PHASE_3G — Governance & Shariah Boundation (`app/services/business_loop/governance.py`)

> No AI outcome authorizes an action; no recommendation is an authorization; ambiguity is held for review. MASTER_PLAN §3.4.

## What was built

A deterministic, AI-independent governance evaluator over **registered actions only**:

| Rule order | Outcome |
|---|---|
| action not in `ACTION_REGISTRY` | **DENIED** (`test_governance_denies_unregistered_action` [V]) |
| Shariah ambiguity flagged | **DEFERRED** → held for qualified review (`test_governance_holds_ambiguity_and_approval` [V]) |
| no qualified Shariah review | **REVIEW_REQUIRED** [V] |
| preconditions missing | **REVIEW_REQUIRED** [V] |
| action requires approval (registry or explicit) | **APPROVAL_REQUIRED** [V] |
| else | **PERMITTED** [V] |

Key properties:
- `certified_by = "deterministic-governance"` — never an AI (asserted [V]).
- Approval binds to an EXACT recommendation version + material hash via `approve_binding` (`recommendation_id:vN:material_hash`) — an approval can never carry over to a changed material (`test_recommendation_version_change_requires_revalidation` [V]).
- `shariah-approved` gates come from qualified review + approved policy (`shariah-reviewed-v1`), never from Jev/LLM.
- In `approval_wait`, the synthetic slice simulates an owner approval and marks it `SYNTHETIC - not a real owner decision` (asserted [V]).

## Gaps

G-3G closed. Approval is simulated in the slice only; production approval flows through `run_agent_approval` / owner surface (documented, not reworked).
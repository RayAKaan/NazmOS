# PHASE_3E — Advisory & Recommendation (`advisory.py`, `recommendation.py`)

> AI is advisory, attribution is exact, and a recommendation binds to the exact evidence that produced it. MASTER_PLAN §10, §5, §22.

## Advisory (`advisory.py`)

- **Typed, validated, attribution-exact**: `AdvisorySource` ∈ {jev, opencode, llm_api, deterministic_only, mocked}. A fallback/deterministic reply is *never* labelled jev (validated by `test_deterministic_only_advisor_never_labels_jev` [V] and slice assertion `advisory["source"] == mocked`).
- **Validation ladder** (§10.6): transport → schema → allowed-value (contract) → capability → deterministic. Out-of-contract suggestions are flagged `OUT_OF_CONTRACT` and **discarded, never coerced** (`test_consult_advisory_rejects_out_of_contract_suggestion` [V]).
- **Deterministic-only fail-closed default**: `deterministic_only_advisor` returns the deterministic decision with no provider consulted.
- Reuses the canonical gateway surface (`ai_gateway.systemone_reason`) — no re-implementation; `canonical_advisor` wires the existing shadow path.

## Recommendation (`recommendation.py`)

- Binds `recommendation_id`, `version`, `opportunity_id`, `state_version`, `evidence_ids`, `action_type`, `potential/expected impact`, `impact_formula_version`, `action_contract_version`, exact `provider`, `advisory_validated`, `policy_version`, `material_hash`.
- **State machine**: `RECOMMENDATION_TRANSITIONS` — invalid transitions raise (`test_recommendation_lifecycle_guards_invalid_transition` [V]).
- **Version bump forces revalidation**: `bump_version` → `version+1`, `advisory_validated=False`, new material hash; a materially changed recommendation can never silently reuse a prior approval (`test_recommendation_version_change_requires_revalidation` [V]).
- Describes to a DLP-clean dict (no PII, opaque ids only). [V]

## Evidence-attribution policy

The recommendation records the **actual provider identity + validation result** (not a warm "jev was consulted"), so the learning loop can trust only what was validated.
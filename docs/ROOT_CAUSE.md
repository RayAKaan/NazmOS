# Root-Cause Engine

Deterministic, evidence-based — never LLM chain-of-thought, never asserts causality without
support.

## Categories

| Finding category | Hypotheses |
|---|---|
| `stockout_risk` | reorder threshold too low, supplier lead time |
| `dead_stock` | low demand (over-purchasing / wrong assortment) |
| `margin_leakage` | supplier cost increase, selling-price mismatch, cost-vs-price compression, missing/low-quality cost data |

Each hypothesis carries: `hypothesis`, `confidence` (`supported | plausible |
insufficient_evidence`), `evidence` (strings), `supporting_values`.

## Confidence semantics

- **supported** — evidence directly supports the hypothesis.
- **plausible** — a reasonable contributor, not proven.
- **insufficient_evidence** — data is insufficient to distinguish causes.

When no model or no data exists → `status = "uncertain"` (never a fabricated cause).

## Root-cause → recommendation (quality gates)

`ROOT_CAUSE_STRATEGIES` maps hypothesis → candidate strategies:
- `supported` → normal recommendation pipeline.
- `plausible` → allowed but `confidence_penalized`.
- `insufficient_evidence` → information-gathering recommendation, never a high-impact action.

Root-cause output is a recommendation *input*; it always passes through strategy ranking →
policy → approval → execution. It can never bypass policy.

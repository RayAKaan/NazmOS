# Replayability

NazmOS is validated through deterministic synthetic replay, not real-time waiting.

## Virtual business clock

`app/utils/clock.py` provides a contextvar-scoped `utcnow()` + `set_virtual_now` /
`advance_days` / `reset_virtual_now`. Production semantics are unchanged (real time unless a
test sets the override). The deterministic evaluation functions (recency, freshness,
operational health) accept an explicit `now` so a test can evaluate "as of" any virtual
timestamp.

## Deterministic inputs → deterministic outputs

- Same synthetic merchant fixture → same findings, root causes, rankings, priorities.
- Recency/freshness/regime shift only with an explicit virtual `now` or a stored timestamp.

## Affected by (and handled deterministically)

- **Time** — via virtual clock + injected timestamps.
- **Database state** — via per-test in-memory SQLite (or Postgres in CI).
- **LLM** — not used in score/policy/impact/attribution; mock mode for anything else.
- **External APIs** — none in the deterministic loop (supplier prices are fixtures).

## Not a production simulator

This is engineering validation only. Real merchant events arrive in real time; the test
system accelerates them for proof.

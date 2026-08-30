# Strategy Adaptation

How historical outcomes, recency, and regime change the *current* recommendation without
erasing evidence or bypassing safety.

## Deterministic ranking (`best_strategy_for_finding`)

```
contextual_score =
    (0.6·effectiveness + 0.4·success_rate)   [evidence-tier weighted]
    × recency_relevance                       [recency-weighted vs raw success]
    × regime_relevance                        [regime_relevance_multiplier(state)]
```

- **effectiveness / success_rate** — raw, from `LearnedOutcome` (never erased).
- **evidence_tier** — `insufficient` (0) / `preliminary` (0.5) / `strong` (1.0), based on raw
  attempt count. A single success never dominates.
- **recency_relevance** — bounded 0.3–1.0; shifts toward recent outcomes but a weak recent
  sample cannot zero out strong history.
- **regime_relevance** — `no_signal`/`insufficient_data`=1.0, `possible_change`=0.7,
  `supported_change`=0.4. Only down-weights *current relevance*; history stays visible.

## Invariant

Ranking decides what is preferable; policy decides what is permissible. Regime/recency
adjustments never grant execution permission, and stability never retains an unsafe strategy.

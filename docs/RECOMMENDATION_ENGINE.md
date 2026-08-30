# Recommendation Engine

Deterministic. The LLM never computes the score, authorizes, or changes policy.

## Score

```
score = 0.15·goal_alignment + 0.20·impact + 0.15·urgency + 0.10·confidence
      + 0.10·data_quality + 0.20·strategy − 0.10·risk
```

Every input is normalized to 0–1 (`decision_scoring.normalize_*`). Impact uses log-scale SAR
(cap SAR 100k); never raw SAR vs percentage.

## Strategy term

Evidence-tier-weighted blend of effectiveness + success rate; `insufficient` evidence
contributes 0 (never masquerades as knowledge).

## Recency + regime

- `strategy_performance.recency_weight` (exponential half-life) weights recent outcomes higher
  **without** rewriting raw history.
- `regime_detection` (deterministic relative-deviation) produces a relevance multiplier that
  down-weights historical evidence when the business materially changed — history is never
  erased, only its current relevance is reduced.

## Stability (hysteresis)

`apply_stability` retains the previous strategy when scores are within `RECOMMENDATION_MIN_DELTA`,
but **never** retains an unsafe (`risk == high`) or unavailable strategy.

## Boundary (invariant)

**Ranking decides what is preferable. Policy decides what is permissible.** A high score
never grants execution permission.

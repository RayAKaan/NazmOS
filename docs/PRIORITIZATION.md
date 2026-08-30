# Prioritization

`services/prioritization.py` is the single canonical problem-prioritization engine, used by
the Action Center, Weekly Report, and (via the shared service) the Mobile Action Center.

## Formula (deterministic, documented)

```
priority = severity(4/3/2/1)
         + urgency(3/2/1/0)
         + 2 if recurring
         + 1 if worsening
         + 1 if goal-aligned
         − 1 if data_quality < 70
         − 1 if stale
```

Tie-break: estimated financial impact (desc). Bounded to top-N. Resolved/verified findings
are excluded (no fake "active" problems).

No LLM, no raw-SAR-vs-percentage mixing.

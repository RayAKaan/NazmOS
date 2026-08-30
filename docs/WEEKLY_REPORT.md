# Weekly Report

`services/weekly_report_service.build_weekly_report` + `services/prioritization.top_problems`.

## Shared prioritization

One deterministic `priority_score` (severity + urgency + recurrence + worsening +
goal-aligned − data-quality penalty − stale penalty) drives BOTH the Weekly Report
(`priorities` field) and the Action Center (`/audits/priorities`). They never disagree.

## Merchant-facing structure

Top section: "What should I know this week?" — top 3–5 problems, then deeper exploration
(impact breakdown, health dimensions, top findings/actions). Observed vs estimated impact
always separated; no fake precision.

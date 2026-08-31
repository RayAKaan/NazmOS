# DESIGN_SYSTEM_VISUAL_REPORT

## Summary

- **Baseline screenshots:** 6 routes under `e2e/__screenshots__/baseline/`
- **Source:** Playwright `toHaveScreenshot` (no external visual-regression service)
- **Delta artifacts:** `test-results/**/*-{expected,actual,diff}.png`
- **Affected routes detected:** 0

## Baseline routes captured

- [/](http://localhost:3000/)
- [/login](http://localhost:3000/login)
- [/privacy](http://localhost:3000/privacy)
- [/product-demo](http://localhost:3000/product-demo)
- [/register](http://localhost:3000/register)
- [/terms](http://localhost:3000/terms)

## Deltas — manual classification required

Every delta must be classified as `EXPECTED CONSOLIDATION` or `UNINTENDED REGRESSION`.
Do not auto-approve all differences.

| Route | Detection | Playwright failure | Classification | Notes |
|---|---|---|---|---|
| [/](http://localhost:3000/) | unknown | pass | | |
| [/login](http://localhost:3000/login) | unknown | pass | | |
| [/privacy](http://localhost:3000/privacy) | unknown | pass | | |
| [/product-demo](http://localhost:3000/product-demo) | unknown | pass | | |
| [/register](http://localhost:3000/register) | unknown | pass | | |
| [/terms](http://localhost:3000/terms) | unknown | pass | | |

## Guide

- **EXPECTED CONSOLIDATION**: previously distinct legacy colors (e.g. `navy-*`, `status-*`, `bg-*`, `text-*`) now map to one canonical Tier-2 token, so several routes shift to the shared color. Accept only if spacing/layout/type are unchanged.
- **UNINTENDED REGRESSION**: any layout, spacing, component-hierarchy, or typography change must be fixed before continuing.

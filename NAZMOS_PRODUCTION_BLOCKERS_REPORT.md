# NazmOS — Production Readiness Blockers & Weaknesses

**Date:** 2026-08-07  
**Scope:** Every weakness currently preventing NazmOS from being safely deployed to real merchants at scale in Saudi Arabia.

---

## How to read this report

Each weakness is rated:
- **Severity:** Critical / High / Medium / Low
- **Blocks real merchant data?** Yes / No
- **Blocks commercial scale?** Yes / No
- **Effort to fix:** Small / Medium / Large

A "Critical" blocker means **do not onboard a real merchant until it is closed or explicitly waived**.

---

## 1. Infrastructure & Platform Reliability

### 1.1 Object storage abstraction is not fully wired into the upload router
- **Severity:** Critical
- **Blocks real merchant data:** Yes
- **Blocks commercial scale:** Yes
- **Evidence:** `backend/app/routers/upload.py` still writes files directly to disk via `aiofiles` in some paths. The `storage.py` abstraction exists but is not used consistently.
- **Risk:** Files stored on local disk are lost on redeploy, not replicated, and cannot scale horizontally. A container restart could erase uploaded merchant data.
- **Fix:** Replace direct disk writes with `storage.store()` / `storage.retrieve()`; use S3/MinIO in production with local fallback only for dev.

### 1.2 Celery/Redis production path is code-only, not runtime-validated
- **Severity:** Critical
- **Blocks real merchant data:** Yes
- **Blocks commercial scale:** Yes
- **Evidence:** Docker is unavailable in the sandbox; all tests run with `USE_CELERY=false`. The zero-cost path is validated, but the production async path (Redis broker, Celery worker) is not.
- **Risk:** Background ingestion, event processing, and adapter syncs may fail silently in production. Memory/timeout issues on large uploads.
- **Fix:** Deploy Redis + Celery worker in staging; run E2E import with `USE_CELERY=true`; monitor task success rate and retry behavior.

### 1.3 Backup/restore discipline does not exist
- **Severity:** Critical
- **Blocks real merchant data:** Yes
- **Blocks commercial scale:** Yes
- **Evidence:** `scripts/backup_postgres.py` and `scripts/restore_postgres.py` exist, but no schedule or restore drill has been performed (`NAZMOS_READINESS_ASSESSMENT.md`).
- **Risk:** A single DB failure or operator error destroys all merchant data with no recovery path.
- **Fix:** Daily automated backups to object storage; monthly restore drill into a fresh DB; documented RTO/RPO.

### 1.4 Sentry/error alerting is not configured
- **Severity:** High
- **Blocks real merchant data:** Yes
- **Blocks commercial scale:** Yes
- **Evidence:** Sentry SDK is installed, but `SENTRY_DSN` is empty in dev and no alerts fire (`NAZMOS_READINESS_ASSESSMENT.md`).
- **Risk:** Production errors go unnoticed until a merchant complains. No incident detection.
- **Fix:** Add DSN to production secrets; route alerts to Slack/PagerDuty; set up uptime/health monitoring.

### 1.5 No high-availability / disaster-recovery design
- **Severity:** High
- **Blocks real merchant data:** Partially
- **Blocks commercial scale:** Yes
- **Evidence:** Single-instance backend design in Docker Compose; no multi-AZ or failover documentation.
- **Risk:** Regional outage or host failure takes the service down for all merchants.
- **Fix:** Document HA architecture; use managed Postgres/Redis; add read replicas; define DR runbook.

### 1.6 Dependency-scan gating is not enforced
- **Severity:** Medium
- **Blocks real merchant data:** No
- **Blocks commercial scale:** Yes
- **Evidence:** CI runs `pip-audit` but does not block on high/critical CVEs (`NAZMOS_READINESS_ASSESSMENT.md`).
- **Risk:** A vulnerable dependency becomes a supply-chain entry point.
- **Fix:** Make CI fail on high/critical CVEs; schedule monthly dependency reviews.

---

## 2. Security, Compliance & Trust

### 2.1 PDPL compliance program is incomplete
- **Severity:** Critical
- **Blocks real merchant data:** Yes
- **Blocks commercial scale:** Yes
- **Evidence:** Privacy/terms pages are "pilot-grade placeholders" (`PRODUCTION_READINESS.md`). No data inventory, DPIA, DPO, or SDAIA National Data Governance Platform registration.
- **Risk:** SDAIA enforcement is active; fines and operational shutdowns are possible. Merchants will ask for compliance proof.
- **Fix:** Conduct PDPL gap assessment; publish Arabic privacy notice; implement data subject rights workflows; register with SDAIA if required.

### 2.2 PII redaction is not audited
- **Severity:** High
- **Blocks real merchant data:** Yes
- **Blocks commercial scale:** Yes
- **Evidence:** Structured logging exists, but PII redaction has not been audited (`NAZMOS_READINESS_ASSESSMENT.md`).
- **Risk:** Merchant emails, phone numbers, and file contents may leak into logs or Sentry.
- **Fix:** Run a PII scan across logs and error payloads; add redaction filters; test with synthetic PII.

### 2.3 No penetration test or security certification
- **Severity:** High
- **Blocks real merchant data:** Yes
- **Blocks commercial scale:** Yes
- **Evidence:** Auth, RBAC, and rate limiting exist, but no third-party security assessment is documented.
- **Risk:** Undiscovered vulnerabilities expose merchant data and credentials.
- **Fix:** Commission a PT; target ISO 27001 or SOC 2 Type I; publish security page.

### 2.4 Credential vault uses a hardcoded fallback master key in dev
- **Severity:** High
- **Blocks real merchant data:** Yes
- **Blocks commercial scale:** Yes
- **Evidence:** `backend/app/services/credential_vault.py` falls back to `"dev-master-key-replace-in-production-32chars"` if `CREDENTIAL_MASTER_KEY` is not set.
- **Risk:** Production deployment could accidentally use the weak key, exposing POS/API credentials.
- **Fix:** Enforce `CREDENTIAL_MASTER_KEY` via secret manager; fail startup if missing in production.

### 2.5 Webhook shared tokens are disabled in production but HMAC secrets may be missing
- **Severity:** Medium
- **Blocks real merchant data:** Yes
- **Blocks commercial scale:** Yes
- **Evidence:** `pos_webhooks.py` disables shared tokens in production and requires HMAC secrets (`FOODICS_WEBHOOK_SECRET`, `SALLA_WEBHOOK_SECRET`). If these env vars are empty, webhooks fail.
- **Risk:** Production integrations with Foodics/Salla break or merchants disable them.
- **Fix:** Add startup check that fails loudly if webhook secrets are unset; document rotation process.

### 2.6 Cross-border data transfer policy is undefined
- **Severity:** Medium
- **Blocks real merchant data:** Yes
- **Blocks commercial scale:** Yes
- **Evidence:** PDPL requires approved mechanisms for transfers outside KSA. No transfer impact assessment or SCCs documented.
- **Risk:** Using non-Saudi cloud regions or third-party AI APIs violates PDPL.
- **Fix:** Host in Saudi region; sign DPAs with processors; document lawful transfer basis.

---

## 3. Data Integrity & Correctness

### 3.1 Schema detection can still misclassify files
- **Severity:** Medium
- **Blocks real merchant data:** Yes
- **Blocks commercial scale:** No
- **Evidence:** The guest-audit service had to be updated to better distinguish sales vs. inventory files. Real merchant exports have messy, non-standard column names.
- **Risk:** A sales file misclassified as inventory produces a useless or misleading Money Audit.
- **Fix:** Expand column-name alias library; add merchant confirmation step; collect failure telemetry.

### 3.2 Money Audit relies on cost and price coverage that merchants often lack
- **Severity:** Medium
- **Blocks real merchant data:** Yes
- **Blocks commercial scale:** No
- **Evidence:** Audit quality score drops when cost_price or sell_price is missing. Many SME exports omit cost data.
- **Risk:** Low-confidence audits erode trust; merchants may see SAR 0 at risk and churn.
- **Fix:** Infer cost from purchase history or supplier catalogs; prompt merchants to upload cost files; explain confidence clearly.

### 3.3 Duplicate item matching across uploads is fragile
- **Severity:** Medium
- **Blocks real merchant data:** Yes
- **Blocks commercial scale:** Yes
- **Evidence:** POS webhooks match items by `name ILIKE '%name[:10]%'` which is approximate and error-prone.
- **Risk:** Sales get attributed to the wrong SKU; stock levels become inaccurate.
- **Fix:** Build canonical item resolution using barcode + SKU + fuzzy name; expose mismatches for review.

### 3.4 Daily summaries and audit period anchoring may drift with real-world time zones
- **Severity:** Low
- **Blocks real merchant data:** No
- **Blocks commercial scale:** No
- **Evidence:** Datetime handling uses `utcnow()` in many places; KSA runs on AST (UTC+3).
- **Risk:** Reports may show wrong "today" or shift Ramadan/weekend patterns.
- **Fix:** Store transaction timestamps in AST or with timezone; add timezone-aware tests.

---

## 4. Integrations & Connectors

### 4.1 Connector implementations are best-effort against public API docs
- **Severity:** High
- **Blocks real merchant data:** Yes
- **Blocks commercial scale:** Yes
- **Evidence:** Zid, Qoyod, and extended Salla adapters were implemented without live credential validation. API shapes may differ by merchant tier or country.
- **Risk:** Connectors fail during onboarding, causing churn.
- **Fix:** Partner with Salla/Zid/Foodics/Qoyod for sandbox accounts; build integration tests against real test environments.

### 4.2 No OAuth flow for merchant authorization
- **Severity:** High
- **Blocks real merchant data:** Yes
- **Blocks commercial scale:** Yes
- **Evidence:** Connectors require manual API key/token entry. No OAuth redirect flow exists.
- **Risk:** Merchants share long-lived credentials insecurely; onboarding friction is high.
- **Fix:** Implement OAuth 2.0 flows for Salla/Zid/Foodics/Qoyod; store tokens securely.

### 4.3 Adapter sync does not handle partial failures or idempotency well
- **Severity:** Medium
- **Blocks real merchant data:** Yes
- **Blocks commercial scale:** Yes
- **Evidence:** POS sync tasks update status but retry/rollback logic is thin. Duplicate orders from webhooks are handled, but bulk sync edge cases are not proven.
- **Risk:** Re-running a sync creates duplicate transactions or missed records.
- **Fix:** Add idempotency keys per record; log every sync step; add reconciliation report.

### 4.4 No connector marketplace discovery
- **Severity:** Low
- **Blocks real merchant data:** No
- **Blocks commercial scale:** Yes
- **Evidence:** Merchants must know which adapter to pick; no in-product detection of their POS/e-commerce platform.
- **Risk:** Onboarding drop-off.
- **Fix:** Auto-detect platform from uploaded file headers or domain; suggest connector.

---

## 5. Frontend, UX & Mobile

### 5.1 No native-feeling mobile app or PWA owner mode
- **Severity:** High
- **Blocks real merchant data:** No
- **Blocks commercial scale:** Yes
- **Evidence:** Frontend is responsive but there is no PWA install prompt, offline support, or push notifications. The owner check-in loop is still web-based.
- **Risk:** Saudi owners run businesses from phones; a web-only experience loses habitual engagement.
- **Fix:** Ship PWA with install prompt, push notifications for critical alerts, and a one-sentence daily briefing screen.

### 5.2 WhatsApp Business API is not integrated
- **Severity:** High
- **Blocks real merchant data:** No
- **Blocks commercial scale:** Yes
- **Evidence:** Money Audit has "Copy WhatsApp" and "Share WhatsApp" links that open `wa.me`. True interactive approvals via WhatsApp Business API are not implemented.
- **Risk:** Manual share/copy breaks the approval loop; merchants forget to return to the app.
- **Fix:** Integrate WhatsApp Business API or a BSP (e.g., Unifonic, Twilio) for interactive message templates with approve/reject buttons.

### 5.3 Arabic UX is translated, not culturally designed
- **Severity:** Medium
- **Blocks real merchant data:** No
- **Blocks commercial scale:** Yes
- **Evidence:** Translations exist, but the UI uses Western data-density patterns. RTL polish and Arabic-first copy need review by native speakers.
- **Risk:** Trust and comprehension suffer; Arabic-first owners may prefer local competitors.
- **Fix:** Hire Arabic UX copywriter; run usability tests with Saudi owners; optimize RTL layouts.

### 5.4 Onboarding still requires a file upload
- **Severity:** Medium
- **Blocks real merchant data:** No
- **Blocks commercial scale:** Yes
- **Evidence:** Even after adding the guest audit, the full onboarding still centers on CSV/Excel upload. Connector-based onboarding is not the default path.
- **Risk:** Many merchants never export files correctly; drop-off before first value.
- **Fix:** Make connector-based import the primary onboarding path; offer file upload as fallback.

### 5.5 Error states are not merchant-friendly
- **Severity:** Medium
- **Blocks real merchant data:** Yes
- **Blocks commercial scale:** No
- **Evidence:** Some error messages expose API details or suggest "contact support" without next steps.
- **Risk:** Merchants get stuck and churn.
- **Fix:** Add actionable error messages, in-product help, and fallback flows (e.g., manual column mapping).

---

## 6. AI, Intelligence & Decision-Making

### 6.1 Intelligence engines are broad but not battle-tested with real outcomes
- **Severity:** High
- **Blocks real merchant data:** No
- **Blocks commercial scale:** Yes
- **Evidence:** Phases 0–7 are implemented, but the learning engine lacks real feedback data. Bayesian updates, graph learning, and A/B holdbacks are documented but not operational.
- **Risk:** Recommendations may be inaccurate; merchants lose trust after a few bad suggestions.
- **Fix:** Start narrow — prove Money Audit accuracy first; then expand intelligence features; collect outcome feedback rigorously.

### 6.2 LLM orchestration may fall back to mock mode
- **Severity:** High
- **Blocks real merchant data:** Yes
- **Blocks commercial scale:** Yes
- **Evidence:** `main.py` warns if `USE_MOCK_LLM=true` in production. The config flag exists and could be misused.
- **Risk:** Merchant-facing AI responses become canned keyword matches instead of real reasoning.
- **Fix:** Disable mock LLM in production via startup check; enforce OpenRouter/OpenAI via env validation.

### 6.3 Explainability is strong but recommendation confidence is not calibrated
- **Severity:** Medium
- **Blocks real merchant data:** No
- **Blocks commercial scale:** Yes
- **Evidence:** Confidence scores are computed but not validated against actual outcomes.
- **Risk:** Overconfident wrong recommendations damage trust.
- **Fix:** Track predicted vs. actual outcome; adjust confidence calibration; show uncertainty ranges.

### 6.4 No model performance monitoring
- **Severity:** Medium
- **Blocks real merchant data:** No
- **Blocks commercial scale:** Yes
- **Evidence:** No dashboards tracking recommendation accuracy, approval rates, or recovered SAR vs. predicted.
- **Risk:** Model degradation goes unnoticed.
- **Fix:** Add metrics: approval rate by recommendation type, predicted vs. actual recovery, drift alerts.

---

## 7. Operations, Support & Customer Success

### 7.1 No formal incident response runbooks
- **Severity:** High
- **Blocks real merchant data:** Yes
- **Blocks commercial scale:** Yes
- **Evidence:** `RUNBOOKS.md` exists but incident response procedures are not detailed.
- **Risk:** 2 AM outage with no escalation path.
- **Fix:** Write incident severity levels, escalation matrix, communication templates, and post-mortem process.

### 7.2 Customer support is not staffed or instrumented
- **Severity:** High
- **Blocks real merchant data:** No
- **Blocks commercial scale:** Yes
- **Evidence:** No in-app support chat, ticket system, or help center.
- **Risk:** Merchants cannot get help; churn spikes.
- **Fix:** Add WhatsApp support channel, help articles, and issue tracking.

### 7.3 No merchant health / churn monitoring
- **Severity:** Medium
- **Blocks real merchant data:** No
- **Blocks commercial scale:** Yes
- **Evidence:** No dashboards tracking activation, retention, or feature usage.
- **Risk:** Churn is discovered too late.
- **Fix:** Instrument product analytics; define activation/retention metrics; build alerts.

### 7.4 Pilot Ops console is internal-only
- **Severity:** Medium
- **Blocks real merchant data:** No
- **Blocks commercial scale:** Yes
- **Evidence:** `/ops` console exists for founders but is not a scalable customer-success tool.
- **Risk:** Manual ops does not scale beyond tens of merchants.
- **Fix:** Automate health checks and proactive outreach; add CS-facing workflows.

---

## 8. Go-to-Market & Business Model

### 8.1 No public case studies or social proof
- **Severity:** High
- **Blocks real merchant data:** No
- **Blocks commercial scale:** Yes
- **Evidence:** Landing page uses synthetic data and generic testimonials.
- **Risk:** Saudi merchants rely heavily on peer proof; without it, conversion is low.
- **Fix:** Document 3–5 real merchant case studies with verified SAR recovered.

### 8.2 Distribution partnerships are not operational
- **Severity:** High
- **Blocks real merchant data:** No
- **Blocks commercial scale:** Yes
- **Evidence:** Accountant/Monshaat advisor program is in the leap strategy but not implemented.
- **Risk:** CAC is too high for direct SME acquisition.
- **Fix:** Launch partner program with referral tracking and training materials.

### 8.3 Pricing is not validated
- **Severity:** Medium
- **Blocks real merchant data:** No
- **Blocks commercial scale:** Yes
- **Evidence:** Prices are set but no A/B tests or willingness-to-pay research is documented.
- **Risk:** Price too high → low conversion; price too low → unsustainable unit economics.
- **Fix:** Run pricing experiments with pilot cohort; measure CAC, LTV, payback.

### 8.4 No marketing engine
- **Severity:** Medium
- **Blocks real merchant data:** No
- **Blocks commercial scale:** Yes
- **Evidence:** No SEO, content, or paid acquisition visible.
- **Risk:** Dependence on founder network limits growth.
- **Fix:** Build content around Saudi retail best practices; run targeted Meta/Google ads; optimize landing page conversion.

### 8.5 Outcome-based pricing is operationally complex
- **Severity:** Medium
- **Blocks real merchant data:** No
- **Blocks commercial scale:** Yes
- **Evidence:** "Pay for recovered value" requires clean baseline measurement and dispute resolution.
- **Risk:** Billing disputes and revenue recognition complexity.
- **Fix:** Start with flat monthly tiers; add outcome-based upsell later.

---

## 9. Team & Execution Risk

### 9.1 Architecture breadth may exceed execution bandwidth
- **Severity:** High
- **Blocks real merchant data:** No
- **Blocks commercial scale:** Yes
- **Evidence:** 15-layer intelligence architecture plus full frontend redesign, connectors, compliance, and GTM is a lot for a startup.
- **Risk:** Team spreads too thin; nothing reaches excellence.
- **Fix:** Ruthlessly prioritize the core money-audit loop; park advanced engines until Phase 1 is dominant.

### 9.2 No documented hiring/team plan for production support
- **Severity:** Medium
- **Blocks real merchant data:** No
- **Blocks commercial scale:** Yes
- **Evidence:** No org chart or role plan for support, sales, or customer success.
- **Risk:** Product scales but team cannot support it.
- **Fix:** Define first hires: customer success, integration engineer, KSA sales/BD.

---

## 10. Summary: What Must Close Before Real Merchant Data

| # | Blocker | Severity |
|---|---|---|
| 1 | Wire object storage into upload router | Critical |
| 2 | Runtime-validate Celery + Redis production path | Critical |
| 3 | Implement daily backups + restore drill | Critical |
| 4 | Complete PDPL compliance program | Critical |
| 5 | Audit and redact PII in logs/Sentry | Critical |
| 6 | Configure Sentry DSN and alerting | Critical |
| 7 | Enforce production credential master key | Critical |
| 8 | Validate connectors with live sandbox credentials | High |
| 9 | Commission penetration test | High |
| 10 | Add incident response runbooks | High |

---

## 11. Summary: What Must Close Before Commercial Scale

| # | Blocker | Severity |
|---|---|---|
| 1 | WhatsApp Business API integration | High |
| 2 | PWA / mobile owner check-in | High |
| 3 | Public case studies | High |
| 4 | Accountant/Monshaat partner program | High |
| 5 | Customer support channel | High |
| 6 | Merchant health / churn analytics | Medium |
| 7 | Recommendation outcome calibration | Medium |
| 8 | Pricing validation | Medium |
| 9 | Marketing engine | Medium |
| 10 | Security certification (ISO 27001 / SOC 2) | Medium |

---

## 12. Recommended Sequence

1. **Week 1–2:** Close Critical blockers 1–7 (storage, Celery/Redis, backups, PDPL basics, PII, Sentry, credential key).
2. **Week 3–4:** Validate connectors with live sandbox credentials; fix schema detection edge cases.
3. **Week 5–8:** Run 20-merchant Riyadh pilot; collect case studies.
4. **Week 9–12:** Launch WhatsApp Business API approvals, PWA owner mode, and partner program.
5. **Month 4–6:** Scale to 100+ merchants; pursue ISO 27001; build CS and marketing functions.

**Until the Critical blockers are closed, NazmOS should remain in founder-led pilot mode with synthetic or explicitly waived test data only.**

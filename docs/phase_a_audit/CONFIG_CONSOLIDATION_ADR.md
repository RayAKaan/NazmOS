# ADR: Config Consolidation

**Status**: ACCEPTED  
**Date**: 2026-08-29  
**Author**: Phase A Audit

---

## 1. Decision

Config is split across **5 layers** with clear precedence. No consolidation needed — document the hierarchy.

---

## 2. Config Layers (Highest → Lowest Precedence)

| Layer | File | Purpose | Precedence |
|-------|------|---------|------------|
| **1. Runtime Override** | `.env.runtime-test` | CI/test-specific overrides (DB_PASSWORD, SECRET_KEY, USE_MOCK_LLM) | **Highest** — loaded last by test runner |
| **2. Docker Compose** | `docker-compose.yml` + `docker-compose.local.yml` | Service env vars (POSTGRES_USER, REDIS_URL, USE_CELERY) | High — container env |
| **3. App Settings** | `backend/app/config.py` (`Settings` class) | Pydantic `BaseSettings` with `.env` file loading | Medium — app-level defaults |
| **4. Local Dev** | `.env.example` / `backend/.env.example` | Developer documentation of required vars | Low — documentation only |
| **5. Defaults** | `Settings` class field defaults | Hardcoded fallbacks in Python | **Lowest** |

---

## 3. File Inventory

| File | Role | Notes |
|------|------|-------|
| `docker-compose.yml` | Staging stack (Postgres, Redis, API, Celery, Nginx, Prometheus, Grafana) | `USE_CELERY=true`, `USE_REDIS=true` |
| `docker-compose.local.yml` | Local dev (Postgres + Redis only, no Celery) | `DB_PASSWORD` from `.env.runtime-test` |
| `docker-compose.sqlite.yml` | Zero-cost mode (SQLite, no Redis/Celery) | `USE_CELERY=false` auto-detected |
| `docker-compose.prod.yml` | Production pilot (Postgres 15, TLS proxy required) | Requires `.env` with secrets |
| `.env.runtime-test` | **CI override** — DB_PASSWORD, SECRET_KEY, USE_MOCK_LLM=true | **Must load last** in test runner |
| `.env.runtime-test.example` | Template for CI | |
| `.env.example` | Root template (LLM keys, provider order) | |
| `backend/.env.example` | Backend template (DB, Redis, secrets) | |
| `backend/app/config.py` | `Settings` class — single source of truth for app | 168 settings, validators, production guards |

---

## 4. Key Config Patterns

### 4.1 Zero-Cost Toggle
```python
# config.py:26-27
USE_CELERY: bool = False
USE_REDIS: bool = False
```
- `docker-compose.yml` sets both to `"true"` (staging)
- `docker-compose.sqlite.yml` omits → defaults to `False`
- `get_settings()` auto-disables if `DATABASE_URL.startswith("sqlite")`

### 4.2 Mock LLM Toggle
```python
USE_MOCK_LLM: bool = True  # default
```
- `.env.runtime-test` sets `USE_MOCK_LLM=true`
- Production validator forbids `USE_MOCK_LLM=true` in `ENVIRONMENT=production`

### 4.3 Provider Order
```python
LLM_PROVIDER_ORDER: str = "groq,google,mock"
@property
def provider_order(self) -> list[str]: ...
```
- Comma-separated string for env compatibility
- Validated against `{"groq", "google", "mock"}`

### 4.4 WhatsApp Mode
```python
WHATSAPP_ENABLED: str = "mock"  # "mock" | "live"
```
- `mock`: logs to console, returns deep-link fallbacks ($0)
- `live`: requires `WHATSAPP_TOKEN` + `WHATSAPP_PHONE_ID`

---

## 5. Drift Points (To Fix)

| Issue | Location | Fix |
|-------|----------|-----|
| `docker-compose.yml` hardcodes `POSTGRES_PASSWORD: nazmos_dev` | Line 6 | Use `${DB_PASSWORD:-nazmos_v5_dev}` like `docker-compose.local.yml` |
| `config.py:8` default `nazmos_dev` vs runtime `nazmos_v5_dev` | Line 8 vs `.env.runtime-test` | Align default to `nazmos_v5_dev` or document mismatch |
| `docker-compose.prod.yml` uses Postgres 15 vs 17 in others | Line 12 | Standardize on 17 |
| No `docker-compose.override.yml` referenced in README | Root | Document local override pattern |

---

## 6. Test Config Loading

Test runner must load `.env.runtime-test` **after** `.env`:
```bash
# In pytest.ini or conftest.py
ENV_FILES = ".env .env.runtime-test"  # last wins
```

Current `conftest.py` sets `TEST_DATABASE_URL` directly — works but bypasses Pydantic validation. Should use `Settings(_env_file=[".env", ".env.runtime-test"])`.

---

## 7. Recommendation

1. **P0**: Align `POSTGRES_PASSWORD` default in `docker-compose.yml` to `${DB_PASSWORD:-nazmos_v5_dev}`
2. **P1**: Update `config.py:8` default to `nazmos_v5_dev` (match runtime)
3. **P2**: Add `docker-compose.override.yml.example` for local dev
4. **P3**: Document config hierarchy in `docs/architecture/config.md`

No code changes needed — config system works correctly with clear precedence.
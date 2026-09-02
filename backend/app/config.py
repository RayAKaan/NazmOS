from pydantic import field_validator, model_validator, ValidationInfo
from pydantic_settings import BaseSettings
from functools import lru_cache
import secrets


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://nazmos:nazmos_dev@localhost:5432/nazmos"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_RECYCLE: int = 1800
    DATABASE_POOL_TIMEOUT: int = 30
    SECRET_KEY: str = "dev-secret-key-change-in-production-minimum-32-chars"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    CORS_ORIGINS: str = "http://localhost:3000"
    CORS_METHODS: str = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Zero-Cost Architecture — when False, FastAPI BackgroundTasks replaces Celery/Redis.
    USE_CELERY: bool = False
    USE_REDIS: bool = False
    USE_CLIENT_ETL: bool = False  # When True, frontend parses CSV via PapaParse (no server-side pandas)
    
    # --- NazmOS KSA Feature Flags ---
    # Nazm Agent – ON by default – $0 cost, rule-based
    AGENT_ENABLED: bool = True
    AGENT_RESTOCK_ENABLED: bool = True
    AGENT_PRICING_ENABLED: bool = True
    AGENT_CASH_ENABLED: bool = True
    AGENT_STAFF_ENABLED: bool = True
    
    # Vertical modules
    VERTICAL_PHARMACY: bool = True
    VERTICAL_FOOD: bool = True
    VERTICAL_AUTO_PARTS: bool = True
    
    # Supplier / compliance & Zero-Cost Trial Magnets
    SUPPLIER_NETWORK_ENABLED: bool = True
    
    # AI Copilot & Saudi Dialect Conversational Commerce
    CHAT_ENABLED: bool = True  # Enabled: Zero-Cost Saudi Dialect WhatsApp & Executive Copilot
    # Commercial Model: Free Trial & Managed Private Cloud AMC
    BILLING_ENABLED: bool = True  # Enabled: Tracks Free Trial usage and Managed AMC licensing
    
    # Zero-Cost Free Trial Settings
    FREE_TRIAL_ENABLED: bool = True
    FREE_TRIAL_DURATION_DAYS: int = 30
    # Legacy Meta "1,000 free monthly service conversations" cap (pre-Nov-2024).
    # Meta now bills per message (Jul 1 2025) and service+utility conversations
    # become chargeable again Oct 1 2026 — repurposed as a soft per-merchant cap
    # for the free trial WhatsApp tier. Keep WHATSAPP_ENABLED=mock for $0.
    USE_META_FREE_TIER_QUOTA: int = 1000

    # LLM / Model Router — direct provider integrations (no gateway).
    # Groq (OpenAI-compatible) and Google Gemini are tried in LLM_PROVIDER_ORDER.
    # "mock" is a dev-only last resort: it is used only when USE_MOCK_LLM=true or
    # when no provider key is configured. Real-provider rate-limit exhaustion
    # never falls back to mock — it yields an honest capacity message instead.
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GOOGLE_AI_API_KEY: str = ""
    GOOGLE_AI_MODEL: str = "gemini-2.5-flash-lite"
    # Comma-separated provider order, e.g. "groq,google,mock". Kept as a plain
    # string so env parsing works across pydantic-settings versions; use the
    # ``provider_order`` property to consume it as a list.
    LLM_PROVIDER_ORDER: str = "groq,google,mock"
    USE_MOCK_LLM: bool = True
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_TOKENS: int = 1000
    # V9 experiment instrumentation: when set, every chat_completion attempt
    # appends one JSONL record (provider, outcome, latency, token usage,
    # prompt fingerprint) so AI cost and traceability can be audited.
    AI_CALL_LEDGER_PATH: str = ""

    # --- Phase A: AI isolation core ---------------------------------------
    # Global kill switch for AI (reasoning/challenge/brain). When False the
    # deterministic engine's decision is used and no LLM/OpenCode is consulted.
    AI_ENABLED: bool = True
    # HMAC key that signs ReasoningCapsules. Production requires >= 32 chars;
    # dev falls back to a value derived from SECRET_KEY so no new env var is
    # required locally.
    NAZMOS_CAPSULE_SIGNING_KEY: str = ""
    NAZMOS_CAPSULE_TTL_SECONDS: int = 90
    # URL of the dedicated isolated OpenCode runner container. When set, the
    # OpenCode brain path posts capsule prompts there instead of spawning a
    # subprocess in the backend container.
    OPENCODE_RUNNER_URL: str = ""
    OPENCODE_RUNNER_TIMEOUT_SECONDS: int = 45
    # Max chars an AI response may be before the output gate rejects it.
    AI_OUTPUT_MAX_CHARS: int = 8000
    # Outbound/inbound DLP is fail-closed. Keep True.
    DLP_STRICT: bool = True
    
    # File Upload
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 15
    ALLOWED_UPLOAD_EXTENSIONS: str = ".csv,.xlsx,.xls"

    # Audit / autonomy configuration (Phase 4 §13). These were hard-coded constants;
    # now configurable WITH conservative safety floors enforced in policy_engine.
    AUDIT_DEBOUNCE_MINUTES: int = 15          # min gap between event-triggered domain audits
    RISK_ESCALATE_MEDIUM_SAR: float = 5000.0  # impact ≥ this escalates low→medium risk
    RISK_ESCALATE_HIGH_SAR: float = 20000.0   # impact ≥ this escalates →high risk
    AGENT_AUTO_MIN_CONFIDENCE: float = 0.90   # min confidence for auto-execution (safety floor)
    # Phase 10 §11/§23: strategy recency + recommendation stability.
    RECENCY_HALF_LIFE_DAYS: float = 90.0      # outcome half-life for recency weighting
    RECOMMENDATION_MIN_DELTA: float = 0.03    # min score delta before a recommendation flips
    # Phase 11 §Part 9: regime-change detection thresholds.
    REGIME_RELATIVE_DEVIATION: float = 0.35   # ≥35% relative deviation → possible change
    REGIME_MIN_RECENT_SAMPLES: int = 3
    REGIME_MIN_HISTORICAL_SAMPLES: int = 6
    # Phase 11 §Part 7: data-freshness thresholds (hours).
    FRESH_INVENTORY_HOURS: float = 96
    FRESH_SALES_HOURS: float = 48
    FRESH_SUPPLIER_PRICE_HOURS: float = 720
    
    # Forecasting
    ENABLE_FORECASTING: bool = True
    ENABLE_ANOMALY_DETECTION: bool = True
    FORECAST_CACHE_TTL_HOURS: int = 24
    MIN_DAYS_FOR_FORECAST: int = 14
    # Prophet already receives SAUDI_HOLIDAYS_DF as the `holidays` table, which
    # models holiday effects within the fit. Manually multiplying interval rows
    # afterwards double-counts those effects (bug found in hardening audit), so
    # the manual event uplift is OFF by default.
    FORECAST_EVENT_UPLIFT_ENABLED: bool = False
    
    # Localization – KSA defaults
    DEFAULT_CURRENCY: str = "SAR"
    DEFAULT_TIMEZONE: str = "Asia/Riyadh"
    DEFAULT_LOCALE: str = "ar-SA"
    
    # Rate Limits
    CHAT_RATE_LIMIT_PER_MINUTE: int = 20
    UPLOAD_RATE_LIMIT_PER_HOUR: int = 20
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10
    
    # POS Webhook secrets (HMAC-SHA256)
    FOODICS_WEBHOOK_SECRET: str = ""
    SALLA_WEBHOOK_SECRET: str = ""
    FOODICS_WEBHOOK_TOKEN: str = ""
    SALLA_WEBHOOK_TOKEN: str = ""

    CREDENTIAL_MASTER_KEY: str = ""

    # WhatsApp Business Cloud API — outbound approvals & notifications.
    # "mock" ($0) logs to console and returns deep-link fallbacks; "live" posts
    # to graph.facebook.com and requires WHATSAPP_TOKEN + WHATSAPP_PHONE_ID.
    WHATSAPP_ENABLED: str = "mock"  # mock | live
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_ID: str = ""

    # WhatsApp webhook security
    WHATSAPP_VERIFY_TOKEN: str = "nazmos_ksa_whatsapp_2026"
    WHATSAPP_APP_SECRET: str = ""  # Meta X-Hub-Signature-256 HMAC secret

    # Demo fixtures/seeding
    ALLOW_DEMO_SEED: bool = False

    # Comma-separated allowlist of platform founder/operator emails. Combined
    # with the users.is_platform_operator flag, this decides which identities
    # hold platform capabilities (ops console, admin tools, nightly scans).
    FOUNDER_EMAILS: str = ""

    # File/object storage abstraction (local disk, S3, or MinIO)
    STORAGE_BACKEND: str = "local"  # local | s3 | minio
    STORAGE_BUCKET: str = ""
    STORAGE_ENDPOINT: str = ""  # e.g. https://s3.amazonaws.com or http://localhost:9000
    STORAGE_ACCESS_KEY: str = ""
    STORAGE_SECRET_KEY: str = ""
    STORAGE_REGION: str = "us-east-1"
    STORAGE_PREFIX: str = ""  # optional key prefix such as "uploads/"
    STORAGE_USE_SSL: bool = True

    # PostgreSQL Row-Level Security — production app role.
    # When set, the application connection issues SET ROLE <role> after
    # setting app.current_tenant_id so RLS policies are enforced even though
    # the migration user is the table owner.
    DATABASE_APP_ROLE: str = ""

    # Observability
    PROMETHEUS_ENABLED: bool = True
    METRICS_TOKEN: str = ""  # When set, /metrics requires X-Metrics-Token to match.
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    SENTRY_PROFILES_SAMPLE_RATE: float = 0.0

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str, info: ValidationInfo) -> str:
        env = info.data.get("ENVIRONMENT", "development")
        if env == "production":
            if v == "dev-secret-key-change-in-production-minimum-32-chars" or len(v) < 32:
                raise ValueError(
                    "SECRET_KEY must be changed in production and be >=32 chars. "
                    "Generate with: python -c 'import secrets; print(secrets.token_urlsafe(48))'"
                )
        return v

    @field_validator("SENTRY_DSN")
    @classmethod
    def validate_sentry_dsn(cls, v: str, info: ValidationInfo) -> str:
        env = info.data.get("ENVIRONMENT", "development")
        if env == "production" and not v:
            raise ValueError(
                "SENTRY_DSN is required in production. Uncaught exceptions must be aggregated and alerted."
            )
        return v

    @field_validator("USE_MOCK_LLM")
    @classmethod
    def validate_mock_llm(cls, v: bool, info: ValidationInfo) -> bool:
        env = info.data.get("ENVIRONMENT", "development")
        if env == "production" and v:
            raise ValueError(
                "USE_MOCK_LLM must be False in production. Merchant-facing LLM responses must use a real model."
            )
        return v

    @field_validator("CREDENTIAL_MASTER_KEY")
    @classmethod
    def validate_credential_master_key(cls, v: str, info: ValidationInfo) -> str:
        env = info.data.get("ENVIRONMENT", "development")
        if env == "production" and (not v or len(v) < 32):
            raise ValueError(
                "CREDENTIAL_MASTER_KEY is required in production and must be >= 32 chars. "
                "It encrypts POS and integration credentials."
            )
        return v

    @field_validator("NAZMOS_CAPSULE_SIGNING_KEY")
    @classmethod
    def validate_capsule_signing_key(cls, v: str, info: ValidationInfo) -> str:
        env = info.data.get("ENVIRONMENT", "development")
        if env == "production" and v and len(v) < 32:
            raise ValueError(
                "NAZMOS_CAPSULE_SIGNING_KEY must be >= 32 chars. Generate with: "
                "python -c 'import secrets; print(secrets.token_urlsafe(48))'"
            )
        return v

    @field_validator("FOODICS_WEBHOOK_SECRET", "SALLA_WEBHOOK_SECRET")
    @classmethod
    def validate_webhook_secrets(cls, v: str, info: ValidationInfo) -> str:
        env = info.data.get("ENVIRONMENT", "development")
        # In production we strongly recommend HMAC secrets; dev can use tokens.
        if env == "production" and not v:
            # We do not raise here because some merchants may not enable these webhooks,
            # but the startup check will fail loudly if any related webhook endpoint is called.
            pass
        return v

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, v: str, info: ValidationInfo) -> str:
        # NOTE: production enforcement lives in validate_production_cross_fields
        # (mode="after") because CORS_ORIGINS is declared before ENVIRONMENT and
        # field validators run in declaration order, so info.data lacks the
        # environment here at production/missing-env construction time.
        return v

    @field_validator("DATABASE_APP_ROLE")
    @classmethod
    def validate_database_app_role(cls, v: str, info: ValidationInfo) -> str:
        env = info.data.get("ENVIRONMENT", "development")
        if env == "production" and not v.strip():
            raise ValueError(
                "DATABASE_APP_ROLE is required in production. RLS policies are "
                "enforced only when the app connection switches to the restricted "
                "role via SET ROLE after setting app.current_tenant_id."
            )
        return v

    @field_validator("WHATSAPP_ENABLED")
    @classmethod
    def validate_whatsapp_enabled(cls, v: str) -> str:
        value = (v or "mock").lower().strip()
        if value not in ("mock", "live"):
            raise ValueError("WHATSAPP_ENABLED must be 'mock' or 'live'")
        return value

    @field_validator("LLM_PROVIDER_ORDER")
    @classmethod
    def validate_llm_provider_order(cls, v: str) -> str:
        allowed = {"groq", "google", "mock"}
        cleaned = []
        for provider in (v or "").split(","):
            provider = (provider or "").strip().lower()
            if provider and provider not in allowed:
                raise ValueError(f"LLM_PROVIDER_ORDER contains unknown provider '{provider}'")
            if provider:
                cleaned.append(provider)
        return ",".join(cleaned) if cleaned else "groq,google,mock"

    @property
    def provider_order(self) -> list[str]:
        """Comma-separated LLM_PROVIDER_ORDER as a list."""
        return [p.strip() for p in (self.LLM_PROVIDER_ORDER or "").split(",") if p.strip()]

    @model_validator(mode="after")
    def validate_production_cross_fields(self) -> "Settings":
        env = self.ENVIRONMENT
        if env != "production":
            return self
        if self.DATABASE_URL.startswith("sqlite"):
            raise ValueError(
                "SQLite is not allowed in production: RLS policies and the "
                "DATABASE_APP_ROLE SET ROLE model (aggressive tenant isolation) "
                "have no meaning on a file-backed database"
            )
        origins = [origin.strip() for origin in (self.CORS_ORIGINS or "").split(",") if origin.strip()]
        if origins:
            for origin in origins:
                if origin == "*":
                    raise ValueError("CORS wildcard '*' is not allowed in production")
                if not origin.startswith(("https://", "http://")):
                    raise ValueError(f"CORS origin must include scheme: {origin}")
        if not self.GROQ_API_KEY and not self.GOOGLE_AI_API_KEY:
            raise ValueError(
                "At least one of GROQ_API_KEY or GOOGLE_AI_API_KEY is required in "
                "production (merchant-facing LLM responses must use a real provider)"
            )
        if self.WHATSAPP_ENABLED == "live" and (
            not self.WHATSAPP_TOKEN or not self.WHATSAPP_PHONE_ID
        ):
            raise ValueError(
                "WHATSAPP_ENABLED=live requires WHATSAPP_TOKEN and WHATSAPP_PHONE_ID"
            )
        return self


@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    # Fail fast in production if using dev secrets or missing required config.
    if s.ENVIRONMENT == "production":
        if "dev-secret-key" in s.SECRET_KEY:
            raise RuntimeError("FATAL: SECRET_KEY is still the dev default in production")
        if not s.SENTRY_DSN:
            raise RuntimeError("FATAL: SENTRY_DSN is required in production")
        if s.USE_MOCK_LLM:
            raise RuntimeError("FATAL: USE_MOCK_LLM must be False in production")
        if not s.GROQ_API_KEY and not s.GOOGLE_AI_API_KEY:
            raise RuntimeError(
                "FATAL: at least one of GROQ_API_KEY or GOOGLE_AI_API_KEY is "
                "required in production (merchant-facing LLM responses must use a real provider)"
            )
        if s.WHATSAPP_ENABLED == "live" and (not s.WHATSAPP_TOKEN or not s.WHATSAPP_PHONE_ID):
            raise RuntimeError(
                "FATAL: WHATSAPP_ENABLED=live requires WHATSAPP_TOKEN and WHATSAPP_PHONE_ID"
            )
        if not s.CREDENTIAL_MASTER_KEY or len(s.CREDENTIAL_MASTER_KEY) < 32:
            raise RuntimeError("FATAL: CREDENTIAL_MASTER_KEY is required in production and must be >= 32 chars")
    # Auto-detect SQLite mode: no Celery/Redis needed
    if s.DATABASE_URL.startswith("sqlite"):
        object.__setattr__(s, "USE_CELERY", False)
        object.__setattr__(s, "USE_REDIS", False)
    return s

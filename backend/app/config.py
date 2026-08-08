from pydantic import field_validator, ValidationInfo
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
    USE_META_FREE_TIER_QUOTA: int = 1000  # Meta 1,000 free monthly service conversations
    
    # LLM / Model Router — OpenRouter is the gateway, not a hardcoded model vendor.
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_SITE_URL: str = "https://nazmak.com"
    OPENROUTER_APP_NAME: str = "NazmOS by Nazmak"
    USE_MOCK_LLM: bool = True
    LLM_MODEL: str = "google/gemma-2-9b-it:free"
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_TOKENS: int = 1000
    
    # File Upload
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 15
    ALLOWED_UPLOAD_EXTENSIONS: str = ".csv,.xlsx,.xls"
    
    # Forecasting
    ENABLE_FORECASTING: bool = True
    ENABLE_ANOMALY_DETECTION: bool = True
    FORECAST_CACHE_TTL_HOURS: int = 24
    MIN_DAYS_FOR_FORECAST: int = 14
    
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

    # WhatsApp webhook security
    WHATSAPP_VERIFY_TOKEN: str = "nazmos_ksa_whatsapp_2026"
    WHATSAPP_APP_SECRET: str = ""  # Meta X-Hub-Signature-256 HMAC secret

    # Demo fixtures/seeding
    ALLOW_DEMO_SEED: bool = False

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
        env = info.data.get("ENVIRONMENT", "development")
        origins = [origin.strip() for origin in (v or "").split(",") if origin.strip()]
        if env == "production":
            for origin in origins:
                if origin == "*":
                    raise ValueError("CORS wildcard '*' is not allowed in production")
                if not origin.startswith(("https://", "http://")):
                    raise ValueError(f"CORS origin must include scheme: {origin}")
        return v


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
        if not s.CREDENTIAL_MASTER_KEY or len(s.CREDENTIAL_MASTER_KEY) < 32:
            raise RuntimeError("FATAL: CREDENTIAL_MASTER_KEY is required in production and must be >= 32 chars")
    # Auto-detect SQLite mode: no Celery/Redis needed
    if s.DATABASE_URL.startswith("sqlite"):
        object.__setattr__(s, "USE_CELERY", False)
        object.__setattr__(s, "USE_REDIS", False)
    return s

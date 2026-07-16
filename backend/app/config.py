from pydantic import field_validator, ValidationInfo
from pydantic_settings import BaseSettings
from functools import lru_cache
import secrets


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://nazmos:nazmos_dev@localhost:5432/nazmos"
    SECRET_KEY: str = "dev-secret-key-change-in-production-minimum-32-chars"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    CORS_ORIGINS: str = "http://localhost:3000"
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

    # WhatsApp webhook security
    WHATSAPP_VERIFY_TOKEN: str = "nazmos_ksa_whatsapp_2026"
    WHATSAPP_APP_SECRET: str = ""  # Meta X-Hub-Signature-256 HMAC secret

    # Demo fixtures/seeding
    ALLOW_DEMO_SEED: bool = False

    # Observability
    PROMETHEUS_ENABLED: bool = True

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


@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    # Fail fast in production if using dev secret
    if s.ENVIRONMENT == "production" and "dev-secret-key" in s.SECRET_KEY:
        raise RuntimeError("FATAL: SECRET_KEY is still the dev default in production")
    # Auto-detect SQLite mode: no Celery/Redis needed
    if s.DATABASE_URL.startswith("sqlite"):
        object.__setattr__(s, "USE_CELERY", False)
        object.__setattr__(s, "USE_REDIS", False)
    return s

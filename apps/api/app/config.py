from pydantic import model_validator
from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AroTrade AI"
    APP_ENV: str = "development"
    APP_URL: str = "https://arotrader.arosoftlabs.com"
    DEBUG: bool = False

    # Database
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "arotrade"
    POSTGRES_USER: str = "arotrade"
    POSTGRES_PASSWORD: str = "change_me"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    JWT_REFRESH_EXPIRATION_DAYS: int = 7

    # Encryption
    ENCRYPTION_KEY: str = ""

    # CORS
    # Comma-separated list of origins. Kept as a plain str field (rather than
    # List[str]) because pydantic-settings tries to JSON-decode env vars for
    # complex-typed fields, which fails for a bare URL or comma-separated list.
    ALLOWED_ORIGINS: str = "http://localhost:3000,https://arotrader.arosoftlabs.com"
    CORS_CREDENTIALS: bool = True

    # Security
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_REQUIRE_UPPERCASE: bool = True
    PASSWORD_REQUIRE_NUMBERS: bool = True
    PASSWORD_REQUIRE_SPECIAL: bool = True

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 100

    # AI Providers
    # Comma-separated provider preference. Supported: xai, openai, anthropic/claude, gemini.
    AI_PROVIDER_ORDER: str = "xai,openai,anthropic,gemini"
    XAI_API_KEY: str = ""
    XAI_MODEL: str = "grok-4.5"
    XAI_BASE_URL: str = "https://api.x.ai/v1"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4.1"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-latest"
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com/v1"
    ANTHROPIC_VERSION: str = "2023-06-01"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash"

    # Trading
    DERIV_APP_ID: str = ""
    DERIV_API_TOKEN_DEMO: str = ""
    DERIV_API_TOKEN_LIVE: str = ""
    METAAPI_TOKEN: str = ""
    METAAPI_REGION: str = "london"
    MAX_LIVE_ORDER_VOLUME: float = 1.0
    MAX_LIVE_RISK_PERCENT: float = 0.25
    MAX_OPEN_TRADES_PER_SYMBOL: int = 1
    MAX_ACCOUNT_EXPOSURE_PERCENT: float = 80.0
    MAX_BROKER_SPREAD_POINTS: float = 0.0

    # Email (optional - notifications are skipped if SMTP_HOST is empty)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@arotrade.com"
    SMTP_FROM_NAME: str = "AroTrade AI"
    ENABLE_LIVE_TRADING: bool = True
    LIVE_TRADING_ALLOWED: bool = True
    NEW_LIVE_ENTRIES_ALLOWED: bool = True
    FREE_MARGIN_RESERVE_PERCENT: float = 10.0
    PAPER_TRADING_ENABLED: bool = True
    DEMO_INITIAL_BALANCE: float = 10000.0
    MIN_SIGNAL_CONFIDENCE: int = 70
    MIN_SIGNAL_RISK_REWARD: float = 1.5

    # Risk Parameters
    DEFAULT_RISK_PER_TRADE: float = 1.0
    MAX_RISK_PER_TRADE: float = 5.0
    MAX_DAILY_LOSS_PERCENT: float = 3.0
    MAX_WEEKLY_LOSS_PERCENT: float = 5.0
    MAX_OPEN_TRADES: int = 5
    MAX_ACCOUNT_DRAWDOWN_PERCENT: float = 25.0
    BLOCK_SIGNAL_ON_NEWS_FETCH_FAILURE: bool = True

    # Backtesting
    MIN_BACKTEST_TRADES: int = 100
    MIN_PROFIT_FACTOR: float = 1.2
    MAX_CONSECUTIVE_LOSSES: int = 5
    ALLOW_MARTINGALE: bool = False

    # Logging
    LOG_LEVEL: str = "INFO"
    AUDIT_LOG_ENABLED: bool = True
    AUDIT_LOG_RETENTION_DAYS: int = 90

    # Automatic Scanner
    SCANNER_ENABLED: bool = True
    SCANNER_DEFAULT_INTERVAL_SECONDS: int = 60
    QUOTE_STALE_AFTER_SECONDS: int = 10
    SIGNAL_ENTRY_MONITOR_ENABLED: bool = True

    # Scanner defaults for new profiles
    SCANNER_DEFAULT_RISK_PERCENT: float = 0.5
    SCANNER_DEFAULT_MAX_POSITIONS: int = 1
    SCANNER_DEFAULT_APPROVAL_REQUIRED: bool = True

    # Market Streaming
    MARKET_STREAM_ENABLED: bool = True

    # Celery Beat
    CELERY_BEAT_ENABLED: bool = True

    class Config:
        env_file = (".env", "../../.env")
        case_sensitive = True

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if self.APP_ENV.strip().lower() != "production":
            return self

        placeholders = (
            "change_me",
            "changeme",
            "placeholder",
            "generate",
            "default",
        )
        for field_name in ("JWT_SECRET", "ENCRYPTION_KEY"):
            value = str(getattr(self, field_name, "") or "").strip()
            lowered = value.lower()
            if len(value) < 32 or any(marker in lowered for marker in placeholders):
                raise ValueError(
                    f"{field_name} must be set to a unique random secret of at least 32 characters in production."
                )
        return self

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


# Create settings instance
settings = Settings()


# Database URL
DATABASE_URL = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"

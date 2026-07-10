from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AroTrade AI"
    APP_ENV: str = "production"
    APP_URL: str = "https://arotrade.aroftlabs.com"
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
    JWT_SECRET: str = "change_me_very_secure_jwt_secret"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    JWT_REFRESH_EXPIRATION_DAYS: int = 7

    # Encryption
    ENCRYPTION_KEY: str = "change_me_32_char_encryption_key"

    # CORS
    # Comma-separated list of origins. Kept as a plain str field (rather than
    # List[str]) because pydantic-settings tries to JSON-decode env vars for
    # complex-typed fields, which fails for a bare URL or comma-separated list.
    ALLOWED_ORIGINS: str = "http://localhost:3000,https://arotrade.aroftlabs.com"
    CORS_CREDENTIALS: bool = True

    # Security
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_REQUIRE_UPPERCASE: bool = True
    PASSWORD_REQUIRE_NUMBERS: bool = True
    PASSWORD_REQUIRE_SPECIAL: bool = True

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 100

    # AI Providers
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Trading
    DERIV_APP_ID: str = ""
    DERIV_API_TOKEN_DEMO: str = ""
    DERIV_API_TOKEN_LIVE: str = ""
    ENABLE_LIVE_TRADING: bool = False

    # Risk Parameters
    DEFAULT_RISK_PER_TRADE: float = 1.0
    MAX_RISK_PER_TRADE: float = 5.0
    MAX_DAILY_LOSS_PERCENT: float = 3.0
    MAX_WEEKLY_LOSS_PERCENT: float = 5.0
    MAX_OPEN_TRADES: int = 5
    MAX_ACCOUNT_DRAWDOWN_PERCENT: float = 25.0

    # Backtesting
    MIN_BACKTEST_TRADES: int = 100
    MIN_PROFIT_FACTOR: float = 1.2
    MAX_CONSECUTIVE_LOSSES: int = 5
    ALLOW_MARTINGALE: bool = False

    # Logging
    LOG_LEVEL: str = "INFO"
    AUDIT_LOG_ENABLED: bool = True
    AUDIT_LOG_RETENTION_DAYS: int = 90

    class Config:
        env_file = ".env"
        case_sensitive = True

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


# Create settings instance
settings = Settings()


# Database URL
DATABASE_URL = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, JSON, Enum, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum
from app.database import Base


# Enums
class UserRole(str, enum.Enum):
    ADMIN = "admin"
    TRADER = "trader"
    VIEWER = "viewer"


class SignalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED_DEMO = "executed_demo"
    EXECUTED_LIVE = "executed_live"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class SignalLifecycleStatus(str, enum.Enum):
    """Full signal lifecycle Ã¢â‚¬â€ replaces the coarse SignalStatus for auto signals."""
    DETECTED = "detected"
    VALIDATING = "validating"
    PENDING_APPROVAL = "pending_approval"
    APPROVED_WAITING_ENTRY = "approved_waiting_entry"
    TRIGGERED = "triggered"
    EXECUTION_PENDING = "execution_pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    OPEN = "open"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    CLOSED = "closed"
    FAILED = "failed"


class ExecutionMode(str, enum.Enum):
    """Distinct execution modes Ã¢â‚¬â€ never confuse paper sim with broker orders."""
    PAPER = "paper"           # Internal simulation Ã¢â‚¬â€ no broker involved
    BROKER_DEMO = "broker_demo"  # Real MetaApi order on an MT5 demo account
    LIVE = "live"             # Real MetaApi order on an MT5 live account


class TradeStatus(str, enum.Enum):
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class TradingMode(str, enum.Enum):
    DEMO = "demo"
    LIVE = "live"


# Models
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role = Column(Enum(UserRole), default=UserRole.TRADER)

    # Account settings
    default_risk_percent = Column(Float, default=1.0)
    max_daily_loss_percent = Column(Float, default=3.0)
    max_open_trades = Column(Integer, default=5)
    trading_mode = Column(Enum(TradingMode), default=TradingMode.DEMO)
    enable_live_trading = Column(Boolean, default=False)

    # Status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    accepted_risk_disclaimer = Column(Boolean, default=False)
    accepted_live_disclaimer = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    last_login = Column(DateTime, nullable=True)

    # Relationships
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    broker_accounts = relationship("BrokerAccount", back_populates="user", cascade="all, delete-orphan")
    strategies = relationship("Strategy", back_populates="user", cascade="all, delete-orphan")
    signals = relationship("Signal", back_populates="user", cascade="all, delete-orphan")
    trades = relationship("Trade", back_populates="user", cascade="all, delete-orphan")
    journal_entries = relationship("JournalEntry", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")
    execution_audits = relationship("ExecutionAudit", back_populates="user", cascade="all, delete-orphan")
    scanner_profiles = relationship("ScannerProfile", back_populates="user", cascade="all, delete-orphan")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(500), index=True, nullable=False)
    refresh_token = Column(String(500), nullable=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="sessions")


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    key = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    last_used = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="api_keys")


class BrokerAccount(Base):
    __tablename__ = "broker_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    broker = Column(String(50), nullable=False)  # deriv, mt5, oanda, etc.
    account_id = Column(String(255), nullable=False)
    account_type = Column(Enum(TradingMode), default=TradingMode.DEMO)
    balance = Column(Float, default=0.0)
    currency = Column(String(3), default="USD")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    # MT5-via-MetaApi connectivity
    name = Column(String(100), nullable=True)
    server = Column(String(100), nullable=True)
    platform = Column(String(10), nullable=True)  # mt4 / mt5
    metaapi_account_id = Column(String(64), nullable=True, unique=True)
    connection_state = Column(String(30), nullable=True)  # undeployed, deploying, deployed, undeploying

    user = relationship("User", back_populates="broker_accounts")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=True)
    category = Column(String(30), default="general")  # signal, trade, system
    link = Column(String(255), nullable=True)
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)


class Symbol(Base):
    __tablename__ = "symbols"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), unique=True, index=True, nullable=False)
    display_name = Column(String(100))
    category = Column(String(50))  # forex, indices, commodities, crypto
    is_active = Column(Boolean, default=True)


class Candle(Base):
    __tablename__ = "candles"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), index=True, nullable=False)
    timeframe = Column(String(10), index=True, nullable=False)  # M1, M5, M15, H1, D1, etc.
    open_price = Column(Float, nullable=False)
    high_price = Column(Float, nullable=False)
    low_price = Column(Float, nullable=False)
    close_price = Column(Float, nullable=False)
    volume = Column(Float, default=0.0)
    timestamp = Column(DateTime, index=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    symbol = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    image_url = Column(String(500), nullable=True)
    prompt = Column(Text, nullable=True)

    # Analysis result (JSON)
    analysis = Column(JSON, nullable=True)
    bias = Column(String(20))  # bullish, bearish, neutral
    signal = Column(String(20))  # buy, sell, hold
    confidence = Column(Integer)  # 0-100

    # Entry/Exit
    entry_min = Column(Float, nullable=True)
    entry_max = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit_1 = Column(Float, nullable=True)
    take_profit_2 = Column(Float, nullable=True)
    take_profit_3 = Column(Float, nullable=True)
    risk_reward = Column(Float, nullable=True)

    reasoning = Column(JSON, nullable=True)  # List of reasons
    invalidation = Column(Text, nullable=True)
    news_warning = Column(Text, nullable=True)
    risk_warning = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    analysis_id = Column(Integer, ForeignKey("ai_analyses.id"), nullable=True)

    # Source metadata (populated for auto-signals)
    source = Column(String(20), nullable=True)          # "manual" or "auto"
    scanner_profile_id = Column(Integer, ForeignKey("scanner_profiles.id"), nullable=True)
    strategy_id = Column(Integer, nullable=True)        # FK to strategies.id
    broker_account_id = Column(Integer, ForeignKey("broker_accounts.id"), nullable=True)

    # Symbols Ã¢â‚¬â€ both canonical and exact broker symbol
    symbol = Column(String(30), nullable=False)         # canonical display symbol
    canonical_symbol = Column(String(30), nullable=True)
    broker_symbol = Column(String(30), nullable=True)   # exact broker symbol (e.g. XAUUSDm)
    timeframe = Column(String(10), nullable=False)
    signal_type = Column(String(20), nullable=False)    # buy, sell

    # Source candle close time (used for fingerprint deduplication)
    source_candle_time = Column(DateTime, nullable=True)

    # Prices
    detected_price = Column(Float, nullable=True)       # price when signal was detected
    latest_price = Column(Float, nullable=True)         # last refreshed broker price

    # Entry/Exit levels
    entry_min = Column(Float, nullable=True)
    entry_max = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit_1 = Column(Float, nullable=True)
    take_profit_2 = Column(Float, nullable=True)
    take_profit_3 = Column(Float, nullable=True)

    risk_reward = Column(Float, nullable=True)
    confidence = Column(Integer, default=50)

    # Legacy status (kept for backward compat)
    status = Column(Enum(SignalStatus), default=SignalStatus.PENDING)

    # Full lifecycle status for auto-signals
    lifecycle_status = Column(String(30), nullable=True)  # detected/validating/pending_approval/...

    notes = Column(Text, nullable=True)

    # AI/Strategy reasoning (JSON arrays)
    reasoning = Column(JSON, nullable=True)             # list[str] of reasons
    invalidation = Column(Text, nullable=True)          # condition that voids this signal
    news_warning = Column(Text, nullable=True)          # upcoming news risk

    # Deduplication fingerprint
    # Built from: scanner_profile_id + broker_account_id + broker_symbol + timeframe +
    #             strategy_id + candle_close_time + direction
    # Unique constraint ensures the same closed candle never generates duplicate signals
    fingerprint = Column(String(128), nullable=True, index=True)
    blocked_reason = Column(Text, nullable=True)

    # Approval action
    approved_action = Column(String(30), nullable=True)  # "wait_for_entry" or "jump_in_now"
    execution_mode = Column(String(20), nullable=True)   # "paper", "broker_demo", "live"

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    approved_at = Column(DateTime, nullable=True)
    triggered_at = Column(DateTime, nullable=True)
    execution_started_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)
    expired_at = Column(DateTime, nullable=True)
    valid_until = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="signals")
    scanner_profile = relationship("ScannerProfile", foreign_keys=[scanner_profile_id])
    broker_account = relationship("BrokerAccount", foreign_keys=[broker_account_id])

    __table_args__ = (
        UniqueConstraint("fingerprint", name="uq_signal_fingerprint"),
    )


class Strategy(Base):
    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Strategy rules (JSON)
    rules = Column(JSON, nullable=True)
    trend_indicators = Column(JSON, nullable=True)
    momentum_indicators = Column(JSON, nullable=True)
    volume_indicators = Column(JSON, nullable=True)
    smart_money = Column(JSON, nullable=True)

    # Risk settings
    risk_per_trade = Column(Float, default=1.0)
    max_daily_loss = Column(Float, nullable=True)
    max_open_trades = Column(Integer, default=1)
    allow_martingale = Column(Boolean, default=False)

    # Status & Scoring
    is_active = Column(Boolean, default=True)
    health_score = Column(Integer, default=0)  # 0-100

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="strategies")


class Backtest(Base):
    __tablename__ = "backtests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)

    symbol = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)

    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    initial_balance = Column(Float, default=10000)

    # Results
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)

    total_profit = Column(Float, default=0.0)
    profit_factor = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    average_win = Column(Float, default=0.0)
    average_loss = Column(Float, default=0.0)
    risk_reward_ratio = Column(Float, default=0.0)

    equity_curve = Column(JSON, nullable=True)
    trades_log = Column(JSON, nullable=True)

    is_safe = Column(Boolean, default=False)
    status = Column(String(20), default="completed")

    created_at = Column(DateTime, server_default=func.now())


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=True)

    symbol = Column(String(20), nullable=False)
    trade_type = Column(String(20), nullable=False)  # buy, sell

    entry_price = Column(Float, nullable=False)
    entry_time = Column(DateTime, nullable=False)

    exit_price = Column(Float, nullable=True)
    exit_time = Column(DateTime, nullable=True)

    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=True)

    volume = Column(Float, nullable=False)
    profit_loss = Column(Float, nullable=True)
    profit_loss_percent = Column(Float, nullable=True)

    status = Column(Enum(TradeStatus), default=TradeStatus.PENDING)
    mode = Column(Enum(TradingMode), default=TradingMode.DEMO)

    # A trade is only considered open after a broker or the explicit paper engine fills it.
    broker = Column(String(50), nullable=True)
    broker_order_id = Column(String(255), unique=True, nullable=True)
    client_order_id = Column(String(255), unique=True, nullable=True)
    execution_status = Column(String(30), nullable=False, default="queued", server_default="queued")
    execution_error = Column(Text, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    filled_at = Column(DateTime, nullable=True)

    notes = Column(Text, nullable=True)

    # MT5 connection & real execution details
    broker_account_id = Column(Integer, ForeignKey("broker_accounts.id"), nullable=True)
    execution_mode = Column(String(20), nullable=True)
    provider = Column(String(50), nullable=True)
    broker_symbol = Column(String(30), nullable=True)
    execution_intent_id = Column(Integer, ForeignKey("execution_intents.id"), nullable=True)
    broker_position_id = Column(String(255), nullable=True)
    broker_deal_id = Column(String(255), nullable=True)
    requested_price = Column(Float, nullable=True)
    actual_fill_price = Column(Float, nullable=True)
    requested_volume = Column(Float, nullable=True)
    actual_volume = Column(Float, nullable=True)
    commission = Column(Float, nullable=True)
    swap = Column(Float, nullable=True)
    broker_profit = Column(Float, nullable=True)
    reconciliation_status = Column(String(50), nullable=True)
    opened_time = Column(DateTime, nullable=True)
    closed_time = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="trades")
    broker_account = relationship("BrokerAccount", foreign_keys=[broker_account_id])
    execution_intent = relationship("ExecutionIntent", foreign_keys=[execution_intent_id])


class ExecutionAudit(Base):
    __tablename__ = "execution_audits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=True)
    trade_id = Column(Integer, ForeignKey("trades.id"), nullable=True)

    broker = Column(String(50), nullable=False)
    mode = Column(String(10), nullable=False)
    outcome = Column(String(30), nullable=False)
    reason = Column(Text, nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="execution_audits")


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    trade_id = Column(Integer, ForeignKey("trades.id"), nullable=True)

    symbol = Column(String(20), nullable=False)
    trade_date = Column(DateTime, nullable=False)

    # Trade details
    strategy = Column(String(255), nullable=True)
    entry_price = Column(Float, nullable=True)
    exit_price = Column(Float, nullable=True)
    result = Column(String(20))  # win, loss, breakeven
    profit_loss = Column(Float, nullable=True)

    # Emotions
    emotion_before = Column(String(50), nullable=True)
    emotion_after = Column(String(50), nullable=True)

    # Analysis
    mistake_category = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    lesson_learned = Column(Text, nullable=True)

    screenshot_url = Column(String(500), nullable=True)
    ai_feedback = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="journal_entries")


class RiskViolation(Base):
    __tablename__ = "risk_violations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    violation_type = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    signal_id = Column(Integer, nullable=True)
    trade_id = Column(Integer, nullable=True)

    severity = Column(String(20))  # low, medium, high, critical
    is_resolved = Column(Boolean, default=False)

    created_at = Column(DateTime, server_default=func.now())


class ExecutionLog(Base):
    __tablename__ = "execution_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    trade_id = Column(Integer, nullable=True)

    action = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False)  # success, failed, pending
    details = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

    broker = Column(String(50), nullable=True)
    broker_response = Column(JSON, nullable=True)

    created_at = Column(DateTime, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    action = Column(String(255), nullable=False)
    resource = Column(String(100), nullable=False)
    resource_id = Column(Integer, nullable=True)

    changes = Column(JSON, nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)

    created_at = Column(DateTime, server_default=func.now(), index=True)

    user = relationship("User", back_populates="audit_logs")


class AdminSetting(Base):
    __tablename__ = "admin_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, index=True, nullable=False)
    value = Column(JSON, nullable=False)
    description = Column(String(255), nullable=True)

    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ---------------------------------------------------------------------------
# BrokerSymbol Ã¢â‚¬â€ canonical-to-broker symbol mapping with full specification
# ---------------------------------------------------------------------------

class BrokerSymbol(Base):
    """
    Maps a canonical symbol name (e.g. XAUUSD) to the exact symbol name used
    by a specific broker account (e.g. XAUUSDm, GOLD, XAUUSDa).

    Never assume broker symbol names.  Always look up this table before
    sending a candle request, signal, or order to MetaApi.
    """
    __tablename__ = "broker_symbols"

    id = Column(Integer, primary_key=True, index=True)
    broker_account_id = Column(Integer, ForeignKey("broker_accounts.id"), nullable=False, index=True)
    canonical_symbol = Column(String(30), nullable=False, index=True)  # XAUUSD, US30, BTCUSD
    broker_symbol = Column(String(30), nullable=False)                 # XAUUSDm, US30.cash, BTCUSDm
    display_name = Column(String(100), nullable=True)
    category = Column(String(30), nullable=True)  # forex, metals, indices, crypto, synthetic

    # Symbol specification (populated from MetaApi)
    digits = Column(Integer, nullable=True)
    point = Column(Float, nullable=True)
    tick_size = Column(Float, nullable=True)
    tick_value = Column(Float, nullable=True)
    contract_size = Column(Float, nullable=True)
    volume_min = Column(Float, nullable=True)
    volume_max = Column(Float, nullable=True)
    volume_step = Column(Float, nullable=True)
    trade_allowed = Column(Boolean, default=True)

    last_refreshed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    broker_account = relationship("BrokerAccount", foreign_keys=[broker_account_id])

    __table_args__ = (
        UniqueConstraint("broker_account_id", "broker_symbol", name="uq_broker_symbol_per_account"),
        Index("ix_broker_symbol_lookup", "broker_account_id", "canonical_symbol"),
    )


# ---------------------------------------------------------------------------
# ScannerProfile Ã¢â‚¬â€ per-user automatic scanner configuration
# ---------------------------------------------------------------------------

class ScannerProfile(Base):
    """
    A user's scanner configuration.  One profile = one broker account + a set
    of symbols, timeframes, strategies, and risk parameters.

    execution_mode is STRICTLY separated:
      - paper        = internal paper simulation (no broker order)
      - broker_demo  = real MetaApi order on an MT5 demo account
      - live         = real MetaApi order on an MT5 live account
    """
    __tablename__ = "scanner_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    broker_account_id = Column(Integer, ForeignKey("broker_accounts.id"), nullable=True, index=True)

    name = Column(String(100), nullable=False)
    execution_mode = Column(String(20), nullable=False, default=ExecutionMode.PAPER.value)

    # What to scan
    symbols = Column(JSON, nullable=True)          # list[str] of canonical symbols
    timeframes = Column(JSON, nullable=True)        # list[str] e.g. ["H1", "H4"]
    active_strategy_ids = Column(JSON, nullable=True)  # list[int]

    # Quality filters
    minimum_confidence = Column(Float, default=70.0)
    minimum_risk_reward = Column(Float, default=1.5)
    max_spread_points = Column(Float, nullable=True)
    maximum_signal_age_minutes = Column(Integer, default=240)

    # Risk
    risk_percent = Column(Float, default=0.5)

    # News blackout
    news_block_before_minutes = Column(Integer, default=30)
    news_block_after_minutes = Column(Integer, default=30)

    # Feature flags
    scan_enabled = Column(Boolean, default=False)
    approval_required = Column(Boolean, default=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="scanner_profiles")
    broker_account = relationship("BrokerAccount", foreign_keys=[broker_account_id])


# ---------------------------------------------------------------------------
# Signal Ã¢â‚¬â€ extended with broker fields and full lifecycle
# ---------------------------------------------------------------------------
# NOTE: The original Signal class at line ~225 remains unchanged for backward
# compatibility.  New auto-signals use the extended fields below.
# We ADD columns via migration; the ORM class here reflects the FINAL schema.
# The Signal class is extended in-place Ã¢â‚¬â€ these patches are applied via
# Alembic migration 005_scanner_signal_lifecycle.py.
#
# Fields added (all nullable for backward compat):
#   source, lifecycle_status, scanner_profile_id, strategy_id,
#   broker_account_id, canonical_symbol, broker_symbol, source_candle_time,
#   detected_price, latest_price, entry_min, entry_max, reasoning,
#   invalidation, news_warning, fingerprint, approved_action,
#   triggered_at, execution_started_at, expired_at, blocked_reason
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# ExecutionIntent Ã¢â‚¬â€ idempotency guard for broker orders
# ---------------------------------------------------------------------------

class ExecutionIntent(Base):
    """
    Created BEFORE calling MetaApi.  Prevents duplicate orders after:
      - Network timeout
      - Celery retry
      - Worker restart
      - API restart

    Unique constraint: one active intent per (signal_id, execution_mode).
    """
    __tablename__ = "execution_intents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=False, index=True)
    broker_account_id = Column(Integer, ForeignKey("broker_accounts.id"), nullable=True)

    execution_mode = Column(String(20), nullable=False)  # paper / broker_demo / live
    idempotency_key = Column(String(128), unique=True, nullable=True)
    client_order_id = Column(String(64), unique=True, nullable=False)

    # Sizing inputs (all stored for audit)
    requested_volume = Column(Float, nullable=True)
    requested_price = Column(Float, nullable=True)
    equity_at_time = Column(Float, nullable=True)
    risk_percent_at_time = Column(Float, nullable=True)
    tick_size_at_time = Column(Float, nullable=True)
    tick_value_at_time = Column(Float, nullable=True)
    stop_loss_distance = Column(Float, nullable=True)
    loss_per_lot = Column(Float, nullable=True)
    raw_volume = Column(Float, nullable=True)

    # Execution state
    status = Column(String(30), nullable=False, default="CREATED")
    execution_state = Column(String(30), nullable=True)
    broker_order_id = Column(String(255), nullable=True)
    broker_position_id = Column(String(255), nullable=True)
    broker_deal_id = Column(String(255), nullable=True)
    broker_deal_ids = Column(JSON, nullable=True)
    request_payload = Column(JSON, nullable=True)
    broker_response = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", foreign_keys=[user_id])
    signal = relationship("Signal", foreign_keys=[signal_id])
    broker_account = relationship("BrokerAccount", foreign_keys=[broker_account_id])

    __table_args__ = (
        UniqueConstraint(
            "signal_id", "execution_mode",
            name="uq_one_active_intent_per_signal_mode",
        ),
    )


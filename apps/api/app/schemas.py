from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from enum import Enum


# Auth Schemas
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    role: str
    trading_mode: str
    enable_live_trading: bool
    accepted_live_disclaimer: bool
    default_risk_percent: float
    max_daily_loss_percent: float
    max_open_trades: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserSettingsUpdate(BaseModel):
    default_risk_percent: Optional[float] = Field(default=None, gt=0, le=5)
    max_daily_loss_percent: Optional[float] = Field(default=None, gt=0, le=25)
    max_open_trades: Optional[int] = Field(default=None, ge=1, le=20)


class LiveTradingUpdate(BaseModel):
    enable: bool
    accept_risk_disclaimer: bool = False


class BrokerAccountCreate(BaseModel):
    broker: str = Field(min_length=2, max_length=50)
    account_id: str = Field(min_length=2, max_length=255)
    balance: float = Field(default=0, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class BrokerAccountResponse(BaseModel):
    id: int
    broker: str
    account_id: str
    account_type: str
    balance: float
    currency: str
    is_active: bool
    created_at: datetime
    name: Optional[str] = None
    server: Optional[str] = None
    platform: Optional[str] = None
    connection_state: Optional[str] = None
    metaapi_account_id: Optional[str] = None

    class Config:
        from_attributes = True


class MT5ConnectRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    login: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=4, max_length=128)
    server: str = Field(min_length=3, max_length=100)
    platform: Literal["mt4", "mt5"] = "mt5"
    account_type: Literal["demo", "live"] = "demo"

    @field_validator("login")
    @classmethod
    def validate_mt_login(cls, value: str) -> str:
        login = value.strip()
        if not login.isdigit():
            raise ValueError("MT5 login must be the numeric account number from your broker, not an email address")
        return login


class SignalLiveExecutionRequest(BaseModel):
    volume: float = Field(gt=0)
    broker_account_id: int
    notes: Optional[str] = None


class NotificationResponse(BaseModel):
    id: int
    title: str
    body: Optional[str]
    category: str
    link: Optional[str]
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


# AI Analysis Schemas
class AIAnalysisRequest(BaseModel):
    symbol: str
    timeframe: str
    image_url: Optional[str] = None
    prompt: Optional[str] = None


class AIAnalysisResponse(BaseModel):
    id: int
    symbol: str
    timeframe: str
    bias: str
    signal: str
    confidence: int
    entry_min: float
    entry_max: float
    stop_loss: float
    take_profit_1: Optional[float]
    take_profit_2: Optional[float]
    take_profit_3: Optional[float]
    risk_reward: float
    reasoning: List[str]
    invalidation: str
    news_warning: Optional[str]
    risk_warning: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# Signal Schemas
class SignalCreate(BaseModel):
    symbol: str
    timeframe: str
    signal_type: Literal["buy", "sell"]
    entry_min: float = Field(gt=0)
    entry_max: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    risk_reward: Optional[float] = Field(default=None, gt=0)
    confidence: int = Field(default=50, ge=0, le=100)
    notes: Optional[str] = None
    valid_until: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_price_structure(self):
        if self.entry_min > self.entry_max:
            raise ValueError("entry_min must be less than or equal to entry_max")

        if self.signal_type == "buy":
            if self.stop_loss >= self.entry_min:
                raise ValueError("Buy signals require a stop loss below the entry range")
            if self.take_profit_1 is not None and self.take_profit_1 <= self.entry_max:
                raise ValueError("Buy signals require take profit above the entry range")
        else:
            if self.stop_loss <= self.entry_max:
                raise ValueError("Sell signals require a stop loss above the entry range")
            if self.take_profit_1 is not None and self.take_profit_1 >= self.entry_min:
                raise ValueError("Sell signals require take profit below the entry range")

        return self


class SignalResponse(BaseModel):
    id: int
    symbol: str
    timeframe: str
    signal_type: str
    entry_min: float
    entry_max: float
    stop_loss: float
    take_profit_1: Optional[float]
    take_profit_2: Optional[float]
    take_profit_3: Optional[float]
    risk_reward: Optional[float]
    confidence: int
    status: str
    created_at: datetime
    approved_at: Optional[datetime]
    executed_at: Optional[datetime]
    valid_until: Optional[datetime]

    class Config:
        from_attributes = True


class SignalEvaluationRequest(BaseModel):
    observed_price: float = Field(gt=0)


class SignalEvaluationResponse(BaseModel):
    eligible: bool
    reasons: List[str]
    calculated_risk_reward: Optional[float]


class SignalPaperExecutionRequest(SignalEvaluationRequest):
    volume: float = Field(gt=0)
    notes: Optional[str] = None


# Strategy Schemas
class StrategyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    trend_indicators: Optional[List[str]] = None
    momentum_indicators: Optional[List[str]] = None
    volume_indicators: Optional[List[str]] = None
    smart_money: Optional[List[str]] = None
    risk_per_trade: float = 1.0
    max_daily_loss: Optional[float] = None
    max_open_trades: int = 1
    allow_martingale: bool = False


class StrategyResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    risk_per_trade: float
    max_open_trades: int
    health_score: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# Backtesting Schemas
class BacktestRequest(BaseModel):
    strategy_id: int
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    initial_balance: float = 10000


class BacktestResponse(BaseModel):
    id: int
    symbol: str
    timeframe: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    max_drawdown: float
    total_profit: float
    risk_reward_ratio: float
    is_safe: bool
    created_at: datetime

    class Config:
        from_attributes = True


# Trading Schemas
class TradeExecute(BaseModel):
    symbol: str
    trade_type: str  # buy, sell
    entry_price: float
    stop_loss: float
    take_profit: Optional[float] = None
    volume: float
    notes: Optional[str] = None


class TradeResponse(BaseModel):
    id: int
    symbol: str
    trade_type: str
    entry_price: float
    entry_time: datetime
    exit_price: Optional[float]
    exit_time: Optional[datetime]
    stop_loss: float
    take_profit: Optional[float]
    volume: float
    profit_loss: Optional[float]
    status: str
    mode: str
    broker: Optional[str] = None
    broker_order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    execution_status: Optional[str] = None
    execution_error: Optional[str] = None
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


# Journal Schemas
class JournalCreate(BaseModel):
    symbol: str
    trade_date: datetime
    strategy: Optional[str] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    result: str  # win, loss, breakeven
    profit_loss: Optional[float] = None
    emotion_before: Optional[str] = None
    emotion_after: Optional[str] = None
    mistake_category: Optional[str] = None
    notes: Optional[str] = None
    lesson_learned: Optional[str] = None


class JournalResponse(BaseModel):
    id: int
    symbol: str
    trade_date: datetime
    strategy: Optional[str]
    result: str
    profit_loss: Optional[float]
    emotion_before: Optional[str]
    emotion_after: Optional[str]
    notes: Optional[str]
    lesson_learned: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# Admin Schemas
class DashboardStats(BaseModel):
    total_users: int
    active_users: int
    total_signals: int
    demo_trades: int
    live_trades: int
    failed_trades: int
    risk_violations: int
    api_errors: int


class AuditLogResponse(BaseModel):
    id: int
    user_id: int
    action: str
    resource: str
    resource_id: Optional[int]
    changes: Optional[Dict[str, Any]]
    created_at: datetime

    class Config:
        from_attributes = True


# Health Check
class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime


class AIHealthResponse(BaseModel):
    status: str
    provider: str
    model: str
    is_available: bool
    timestamp: datetime

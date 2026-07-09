from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
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
    is_active: bool
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
    signal_type: str  # buy, sell
    entry_min: float
    entry_max: float
    stop_loss: float
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    risk_reward: Optional[float] = None
    confidence: int = 50
    notes: Optional[str] = None


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

    class Config:
        from_attributes = True


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

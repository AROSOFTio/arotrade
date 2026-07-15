from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class DrawingSource(str, Enum):
    DETERMINISTIC = "deterministic"
    AI = "ai"
    SCANNER = "scanner"
    MANUAL = "manual"


MarketBias = Literal["bullish", "bearish", "neutral"]
MarketTrend = Literal["uptrend", "downtrend", "range"]
MarketVolatility = Literal["low", "normal", "high"]
MarketStructureBias = Literal["bullish", "bearish", "mixed"]
SignalAction = Literal["BUY", "SELL", "WAIT", "AVOID"]
DrawingState = str


class ChartCandle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None


class ChartPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time: datetime
    price: float


class FibonacciLevel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ratio: float
    price: float
    label: str


class DrawingStyle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_color: Optional[str] = None
    fill_color: Optional[str] = None
    text_color: Optional[str] = None
    line_width: int = 1
    line_style: Literal["solid", "dashed", "dotted"] = "solid"
    opacity: float = 0.2
    z_index: int = 0


class DrawingInvalidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Optional[str] = None
    reason: Optional[str] = None
    invalidated_at: Optional[datetime] = None
    invalidated_by_price: Optional[float] = None
    invalidated_by_time: Optional[datetime] = None
    related_drawing_id: Optional[str] = None


class BaseDrawing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: str
    symbol: str
    timeframe: str
    source: DrawingSource
    confidence: int = Field(ge=0, le=100)
    label: str
    enabled: bool = True
    created_at: datetime
    expires_at: Optional[datetime] = None
    style: DrawingStyle = Field(default_factory=DrawingStyle)
    time_start: Optional[datetime] = None
    time_end: Optional[datetime] = None
    price_start: Optional[float] = None
    price_end: Optional[float] = None
    price_low: Optional[float] = None
    price_high: Optional[float] = None
    entry_low: Optional[float] = None
    entry_high: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    target_price: Optional[float] = None
    anchor_points: list[ChartPoint] = Field(default_factory=list)
    levels: list[FibonacciLevel] = Field(default_factory=list)
    state: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    invalidation: Optional[DrawingInvalidation] = None


class HorizontalLineDrawing(BaseDrawing):
    type: Literal["horizontal_line"] = "horizontal_line"


class TrendLineDrawing(BaseDrawing):
    type: Literal["trend_line"] = "trend_line"


class RayDrawing(BaseDrawing):
    type: Literal["ray"] = "ray"


class RectangleDrawing(BaseDrawing):
    type: Literal["rectangle"] = "rectangle"


class SupportZoneDrawing(BaseDrawing):
    type: Literal["support_zone"] = "support_zone"


class ResistanceZoneDrawing(BaseDrawing):
    type: Literal["resistance_zone"] = "resistance_zone"


class SupplyZoneDrawing(BaseDrawing):
    type: Literal["supply_zone"] = "supply_zone"


class DemandZoneDrawing(BaseDrawing):
    type: Literal["demand_zone"] = "demand_zone"


class OrderBlockDrawing(BaseDrawing):
    type: Literal["order_block"] = "order_block"


class BreakerBlockDrawing(BaseDrawing):
    type: Literal["breaker_block"] = "breaker_block"


class FairValueGapDrawing(BaseDrawing):
    type: Literal["fair_value_gap"] = "fair_value_gap"


class LiquidityZoneDrawing(BaseDrawing):
    type: Literal["liquidity_zone"] = "liquidity_zone"


class SwingHighDrawing(BaseDrawing):
    type: Literal["swing_high"] = "swing_high"


class SwingLowDrawing(BaseDrawing):
    type: Literal["swing_low"] = "swing_low"


class FibonacciDrawing(BaseDrawing):
    type: Literal["fibonacci"] = "fibonacci"


class EntryZoneDrawing(BaseDrawing):
    type: Literal["entry_zone"] = "entry_zone"


class StopLossDrawing(BaseDrawing):
    type: Literal["stop_loss"] = "stop_loss"


class TakeProfitDrawing(BaseDrawing):
    type: Literal["take_profit"] = "take_profit"


class RiskRewardBoxDrawing(BaseDrawing):
    type: Literal["risk_reward_box"] = "risk_reward_box"


class TextLabelDrawing(BaseDrawing):
    type: Literal["text_label"] = "text_label"


class SignalMarkerDrawing(BaseDrawing):
    type: Literal["signal_marker"] = "signal_marker"


ChartDrawing = Annotated[
    Union[
        HorizontalLineDrawing,
        TrendLineDrawing,
        RayDrawing,
        RectangleDrawing,
        SupportZoneDrawing,
        ResistanceZoneDrawing,
        SupplyZoneDrawing,
        DemandZoneDrawing,
        OrderBlockDrawing,
        BreakerBlockDrawing,
        FairValueGapDrawing,
        LiquidityZoneDrawing,
        SwingHighDrawing,
        SwingLowDrawing,
        FibonacciDrawing,
        EntryZoneDrawing,
        StopLossDrawing,
        TakeProfitDrawing,
        RiskRewardBoxDrawing,
        TextLabelDrawing,
        SignalMarkerDrawing,
    ],
    Field(discriminator="type"),
]


class MarketState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bias: MarketBias = "neutral"
    trend: MarketTrend = "range"
    volatility: MarketVolatility = "normal"
    structure: MarketStructureBias = "mixed"
    current_price: Optional[float] = None
    atr: Optional[float] = None


class IndicatorSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ema20: Optional[float] = None
    ema50: Optional[float] = None
    ema200: Optional[float] = None
    rsi14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    atr14: Optional[float] = None


class SignalSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: SignalAction = "WAIT"
    confidence: int = Field(default=0, ge=0, le=100)
    entry_min: Optional[float] = None
    entry_max: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    risk_reward: Optional[float] = None
    invalidation: Optional[str] = None
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExplanationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = ""
    observations: list[str] = Field(default_factory=list)
    plan: str = ""
    risk_note: str = ""


class ChartAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    broker_symbol: str
    timeframe: str
    generated_at: datetime
    last_candle_time: datetime
    analysis_version: str = "1.0"
    market_state: MarketState
    indicators: IndicatorSummary
    drawings: list[ChartDrawing] = Field(default_factory=list)
    signal: SignalSummary
    explanation: ExplanationSummary
    warnings: list[str] = Field(default_factory=list)

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any, Iterable, Optional

from app.services.scanner.indicators import atr, ema, macd, rsi, trend_structure

from .models import (
    ChartCandle,
    ChartPoint,
    DrawingSource,
    HorizontalLineDrawing,
    MarketBias,
    MarketState,
    MarketStructureBias,
    MarketTrend,
    MarketVolatility,
    SwingHighDrawing,
    SwingLowDrawing,
    TextLabelDrawing,
)


def parse_chart_time(value: object) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        if value > 10_000_000_000:
            value = value / 1000.0
        return datetime.fromtimestamp(float(value), UTC)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def timeframe_to_seconds(timeframe: str) -> int:
    tf = timeframe.upper()
    mapping = {
        "M1": 60,
        "M2": 120,
        "M3": 180,
        "M5": 300,
        "M15": 900,
        "M30": 1800,
        "H1": 3600,
        "H2": 7200,
        "H4": 14_400,
        "D1": 86_400,
        "W1": 604_800,
    }
    return mapping.get(tf, 3600)


def normalize_candles(candles: Iterable[dict]) -> list[ChartCandle]:
    normalized: list[ChartCandle] = []
    seen: set[datetime] = set()
    for candle in candles:
        time = parse_chart_time(candle.get("time") or candle.get("brokerTime") or candle.get("broker_time"))
        if time is None or time in seen:
            continue
        seen.add(time)
        try:
            normalized.append(
                ChartCandle(
                    time=time,
                    open=float(candle["open"]),
                    high=float(candle["high"]),
                    low=float(candle["low"]),
                    close=float(candle["close"]),
                    volume=float(candle["volume"]) if candle.get("volume") is not None else None,
                )
            )
        except (TypeError, ValueError, KeyError):
            continue
    normalized.sort(key=lambda item: item.time)
    return normalized


@dataclass(slots=True)
class SwingPoint:
    index: int
    time: datetime
    price: float
    kind: str  # "high" | "low"
    strength: float
    confirmed_at: datetime


@dataclass(slots=True)
class StructureEvent:
    kind: str  # "BOS" | "CHOCH"
    direction: str  # "bullish" | "bearish"
    index: int
    time: datetime
    level: float
    description: str


@dataclass(slots=True)
class StructureSnapshot:
    bias: MarketBias
    trend: MarketTrend
    volatility: MarketVolatility
    structure: MarketStructureBias
    current_price: float
    atr: Optional[float]
    ema20: Optional[float]
    ema50: Optional[float]
    ema200: Optional[float]
    rsi14: Optional[float]
    macd: Optional[float]
    macd_signal: Optional[float]
    macd_histogram: Optional[float]
    swing_highs: list[SwingPoint] = field(default_factory=list)
    swing_lows: list[SwingPoint] = field(default_factory=list)
    events: list[StructureEvent] = field(default_factory=list)
    higher_highs: bool = False
    higher_lows: bool = False
    lower_highs: bool = False
    lower_lows: bool = False


def _swing_strength(index: int, price: float, candles: list[ChartCandle], lookback: int) -> float:
    window = candles[max(0, index - lookback) : min(len(candles), index + lookback + 1)]
    if not window:
        return 0.0
    ranges = [item.high - item.low for item in window]
    if not ranges:
        return 0.0
    local_atr = median(ranges)
    if local_atr <= 0:
        return 0.0
    left = candles[max(0, index - lookback):index]
    right = candles[index + 1 : min(len(candles), index + lookback + 1)]
    left_span = max((item.high for item in left), default=price) - min((item.low for item in left), default=price)
    right_span = max((item.high for item in right), default=price) - min((item.low for item in right), default=price)
    return round((left_span + right_span) / (2 * local_atr), 3)


def confirmed_swing_highs(candles: list[ChartCandle], lookback: int = 3) -> list[SwingPoint]:
    swings: list[SwingPoint] = []
    if len(candles) < lookback * 2 + 1:
        return swings
    for index in range(lookback, len(candles) - lookback):
        high = candles[index].high
        left = candles[index - lookback : index]
        right = candles[index + 1 : index + lookback + 1]
        if all(high >= item.high for item in left) and all(high > item.high for item in right):
            swings.append(
                SwingPoint(
                    index=index,
                    time=candles[index].time,
                    price=high,
                    kind="high",
                    strength=_swing_strength(index, high, candles, lookback),
                    confirmed_at=candles[index + lookback].time,
                )
            )
    return swings


def confirmed_swing_lows(candles: list[ChartCandle], lookback: int = 3) -> list[SwingPoint]:
    swings: list[SwingPoint] = []
    if len(candles) < lookback * 2 + 1:
        return swings
    for index in range(lookback, len(candles) - lookback):
        low = candles[index].low
        left = candles[index - lookback : index]
        right = candles[index + 1 : index + lookback + 1]
        if all(low <= item.low for item in left) and all(low < item.low for item in right):
            swings.append(
                SwingPoint(
                    index=index,
                    time=candles[index].time,
                    price=low,
                    kind="low",
                    strength=_swing_strength(index, low, candles, lookback),
                    confirmed_at=candles[index + lookback].time,
                )
            )
    return swings


def _higher_or_lower(series: list[SwingPoint], *, direction: str) -> bool:
    if len(series) < 2:
        return False
    recent = series[-3:]
    prices = [item.price for item in recent]
    if len(prices) < 2:
        return False
    if direction == "higher":
        return all(later > earlier for earlier, later in zip(prices, prices[1:]))
    return all(later < earlier for earlier, later in zip(prices, prices[1:]))


def _detect_structure_events(
    candles: list[ChartCandle],
    swing_highs: list[SwingPoint],
    swing_lows: list[SwingPoint],
    atr_value: Optional[float],
) -> list[StructureEvent]:
    events: list[StructureEvent] = []
    if not candles or not swing_highs or not swing_lows:
        return events

    current = candles[-1].close
    buffer = (atr_value or 0.0) * 0.15
    last_high = swing_highs[-1]
    last_low = swing_lows[-1]

    if current > last_high.price + buffer:
        events.append(
            StructureEvent(
                kind="BOS",
                direction="bullish",
                index=last_high.index,
                time=candles[-1].time,
                level=last_high.price,
                description=f"Close broke above the last confirmed swing high at {last_high.price:.5f}",
            )
        )
    if current < last_low.price - buffer:
        events.append(
            StructureEvent(
                kind="BOS",
                direction="bearish",
                index=last_low.index,
                time=candles[-1].time,
                level=last_low.price,
                description=f"Close broke below the last confirmed swing low at {last_low.price:.5f}",
            )
        )

    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        if swing_highs[-1].price > swing_highs[-2].price and swing_lows[-1].price > swing_lows[-2].price:
            if current < swing_lows[-1].price - buffer:
                events.append(
                    StructureEvent(
                        kind="CHOCH",
                        direction="bearish",
                        index=swing_lows[-1].index,
                        time=candles[-1].time,
                        level=swing_lows[-1].price,
                        description="Higher-low structure failed and closed below the most recent swing low.",
                    )
                )
        if swing_highs[-1].price < swing_highs[-2].price and swing_lows[-1].price < swing_lows[-2].price:
            if current > swing_highs[-1].price + buffer:
                events.append(
                    StructureEvent(
                        kind="CHOCH",
                        direction="bullish",
                        index=swing_highs[-1].index,
                        time=candles[-1].time,
                        level=swing_highs[-1].price,
                        description="Lower-high structure failed and closed above the most recent swing high.",
                    )
                )
    return events


def detect_market_structure(candles: list[ChartCandle], timeframe: str) -> StructureSnapshot:
    closes = [candle.close for candle in candles]
    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)
    rsi14 = rsi(closes, 14)
    macd_values = macd(closes)
    atr14 = atr([candle.model_dump() for candle in candles], 14)
    current_price = closes[-1] if closes else 0.0

    swing_highs = confirmed_swing_highs(candles, lookback=3)
    swing_lows = confirmed_swing_lows(candles, lookback=3)
    events = _detect_structure_events(candles, swing_highs, swing_lows, atr14)

    higher_highs = _higher_or_lower(swing_highs, direction="higher")
    higher_lows = _higher_or_lower(swing_lows, direction="higher")
    lower_highs = _higher_or_lower(swing_highs, direction="lower")
    lower_lows = _higher_or_lower(swing_lows, direction="lower")

    ema_bias: MarketBias = "neutral"
    if ema20 is not None and ema50 is not None:
        if ema20 > ema50:
            ema_bias = "bullish"
        elif ema20 < ema50:
            ema_bias = "bearish"

    trend_reading = trend_structure(closes)
    if trend_reading == "bullish" and higher_highs and higher_lows:
        trend: MarketTrend = "uptrend"
    elif trend_reading == "bearish" and lower_highs and lower_lows:
        trend = "downtrend"
    else:
        trend = "range"

    if trend == "uptrend" and ema_bias == "bullish":
        bias: MarketBias = "bullish"
    elif trend == "downtrend" and ema_bias == "bearish":
        bias = "bearish"
    else:
        bias = "neutral"

    structure: MarketStructureBias = "mixed"
    if higher_highs and higher_lows:
        structure = "bullish"
    elif lower_highs and lower_lows:
        structure = "bearish"

    if atr14 is None or current_price <= 0:
        volatility: MarketVolatility = "normal"
    else:
        atr_pct = atr14 / current_price
        if atr_pct < 0.002:
            volatility = "low"
        elif atr_pct > 0.006:
            volatility = "high"
        else:
            volatility = "normal"

    return StructureSnapshot(
        bias=bias,
        trend=trend,
        volatility=volatility,
        structure=structure,
        current_price=current_price,
        atr=atr14,
        ema20=ema20,
        ema50=ema50,
        ema200=ema200,
        rsi14=rsi14,
        macd=macd_values["macd"] if macd_values else None,
        macd_signal=macd_values["signal"] if macd_values else None,
        macd_histogram=macd_values["histogram"] if macd_values else None,
        swing_highs=swing_highs,
        swing_lows=swing_lows,
        events=events,
        higher_highs=higher_highs,
        higher_lows=higher_lows,
        lower_highs=lower_highs,
        lower_lows=lower_lows,
    )


def _marker_style(color: str, fill: str, width: int = 1) -> dict[str, Any]:
    return {
        "line_color": color,
        "fill_color": fill,
        "line_width": width,
        "opacity": 0.25,
    }


def build_structure_drawings(
    *,
    symbol: str,
    timeframe: str,
    candles: list[ChartCandle],
    structure: StructureSnapshot,
    created_at: datetime,
) -> list[object]:
    drawings: list[object] = []
    last_time = candles[-1].time if candles else created_at
    visible_highs = sorted(structure.swing_highs[-6:], key=lambda item: item.time)
    visible_lows = sorted(structure.swing_lows[-6:], key=lambda item: item.time)

    for swing in visible_highs:
        drawings.append(
            SwingHighDrawing(
                id=f"{symbol}:{timeframe}:swing-high:{swing.index}",
                symbol=symbol,
                timeframe=timeframe,
                source=DrawingSource.DETERMINISTIC,
                confidence=min(95, 55 + int(swing.strength * 10)),
                label="Swing high",
                enabled=True,
                created_at=created_at,
                time_start=swing.time,
                time_end=last_time,
                price_start=swing.price,
                price_end=swing.price,
                style=_marker_style("#b91c1c", "#fee2e2"),
                metadata={"index": swing.index, "strength": swing.strength, "confirmed_at": swing.confirmed_at.isoformat()},
            )
        )

    for swing in visible_lows:
        drawings.append(
            SwingLowDrawing(
                id=f"{symbol}:{timeframe}:swing-low:{swing.index}",
                symbol=symbol,
                timeframe=timeframe,
                source=DrawingSource.DETERMINISTIC,
                confidence=min(95, 55 + int(swing.strength * 10)),
                label="Swing low",
                enabled=True,
                created_at=created_at,
                time_start=swing.time,
                time_end=last_time,
                price_start=swing.price,
                price_end=swing.price,
                style=_marker_style("#15803d", "#dcfce7"),
                metadata={"index": swing.index, "strength": swing.strength, "confirmed_at": swing.confirmed_at.isoformat()},
            )
        )

    for event in structure.events:
        label = f"{event.kind} {event.direction.upper()}"
        drawings.append(
            HorizontalLineDrawing(
                id=f"{symbol}:{timeframe}:{event.kind.lower()}:{event.index}:{event.direction}",
                symbol=symbol,
                timeframe=timeframe,
                source=DrawingSource.DETERMINISTIC,
                confidence=78 if event.kind == "BOS" else 72,
                label=label,
                enabled=True,
                created_at=created_at,
                time_start=event.time,
                time_end=last_time,
                price_start=event.level,
                price_end=event.level,
                style={
                    "line_color": "#2563eb" if event.direction == "bullish" else "#dc2626",
                    "line_width": 2,
                    "line_style": "dashed",
                    "opacity": 0.35,
                },
                metadata={"description": event.description, "kind": event.kind, "direction": event.direction, "source_index": event.index},
            )
        )
        drawings.append(
            TextLabelDrawing(
                id=f"{symbol}:{timeframe}:{event.kind.lower()}-label:{event.index}:{event.direction}",
                symbol=symbol,
                timeframe=timeframe,
                source=DrawingSource.DETERMINISTIC,
                confidence=78 if event.kind == "BOS" else 72,
                label=event.description,
                enabled=True,
                created_at=created_at,
                time_start=event.time,
                time_end=last_time,
                price_start=event.level,
                price_end=event.level,
                style={
                    "line_color": "#2563eb" if event.direction == "bullish" else "#dc2626",
                    "fill_color": "#ffffff",
                    "text_color": "#0f172a",
                    "line_width": 0,
                    "opacity": 0.0,
                },
                metadata={"kind": event.kind, "direction": event.direction, "source_index": event.index},
            )
        )

    if structure.higher_highs and structure.higher_lows:
        drawings.append(
            TextLabelDrawing(
                id=f"{symbol}:{timeframe}:structure:bullish",
                symbol=symbol,
                timeframe=timeframe,
                source=DrawingSource.DETERMINISTIC,
                confidence=74,
                label="Higher highs and higher lows",
                enabled=True,
                created_at=created_at,
                time_start=candles[-min(len(candles), 8)].time if candles else created_at,
                time_end=last_time,
                price_start=structure.current_price,
                price_end=structure.current_price,
                style={"line_color": "#15803d", "text_color": "#166534", "line_width": 0, "opacity": 0.0},
                metadata={"structure": "bullish"},
            )
        )
    elif structure.lower_highs and structure.lower_lows:
        drawings.append(
            TextLabelDrawing(
                id=f"{symbol}:{timeframe}:structure:bearish",
                symbol=symbol,
                timeframe=timeframe,
                source=DrawingSource.DETERMINISTIC,
                confidence=74,
                label="Lower highs and lower lows",
                enabled=True,
                created_at=created_at,
                time_start=candles[-min(len(candles), 8)].time if candles else created_at,
                time_end=last_time,
                price_start=structure.current_price,
                price_end=structure.current_price,
                style={"line_color": "#b91c1c", "text_color": "#991b1b", "line_width": 0, "opacity": 0.0},
                metadata={"structure": "bearish"},
            )
        )

    return drawings

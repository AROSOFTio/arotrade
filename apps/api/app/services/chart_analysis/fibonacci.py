from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.services.scanner.indicators import atr

from .market_structure import StructureSnapshot, SwingPoint
from .models import ChartCandle, ChartPoint, DrawingSource, FibonacciDrawing, FibonacciLevel


def _as_pairs(highs: list[SwingPoint], lows: list[SwingPoint]) -> list[tuple[SwingPoint, SwingPoint]]:
    swings = sorted(highs + lows, key=lambda item: item.index)
    pairs: list[tuple[SwingPoint, SwingPoint]] = []
    for left, right in zip(swings, swings[1:]):
        if left.kind == right.kind:
            continue
        pairs.append((left, right))
    return pairs


def _impulse_range(start: SwingPoint, end: SwingPoint) -> float:
    return abs(end.price - start.price)


def _levels_for_range(start: SwingPoint, end: SwingPoint) -> list[FibonacciLevel]:
    ratios = [0.0, 0.382, 0.5, 0.618, 0.786, 1.0]
    high = max(start.price, end.price)
    low = min(start.price, end.price)
    bullish = end.price > start.price
    levels: list[FibonacciLevel] = []
    for ratio in ratios:
        if bullish:
            price = high - (high - low) * ratio
        else:
            price = low + (high - low) * ratio
        levels.append(
            FibonacciLevel(
                ratio=ratio,
                price=round(price, 6),
                label=f"{ratio:.3f}".rstrip("0").rstrip(".") or "0",
            )
        )
    return levels


def detect_fibonacci(
    *,
    symbol: str,
    timeframe: str,
    candles: list[ChartCandle],
    structure: StructureSnapshot,
    created_at: datetime,
) -> list[FibonacciDrawing]:
    if len(candles) < 8 or not structure.swing_highs or not structure.swing_lows:
        return []

    atr_value = structure.atr or atr([candle.model_dump() for candle in candles], 14) or (candles[-1].close * 0.001)
    minimum_range = max(atr_value * 2.2, candles[-1].close * 0.0025)

    all_swings = sorted(structure.swing_highs + structure.swing_lows, key=lambda item: item.index)
    if len(all_swings) < 2:
        return []

    selected: Optional[tuple[SwingPoint, SwingPoint]] = None
    for left, right in reversed(list(zip(all_swings, all_swings[1:]))):
        if left.kind == right.kind:
            continue
        if _impulse_range(left, right) < minimum_range:
            continue
        selected = (left, right)
        break

    if not selected:
        return []

    start, end = selected
    bullish = end.price > start.price
    if bullish and not (start.kind == "low" and end.kind == "high"):
        return []
    if not bullish and not (start.kind == "high" and end.kind == "low"):
        return []

    return [
        FibonacciDrawing(
            id=f"{symbol}:{timeframe}:fibonacci:{start.index}:{end.index}",
            symbol=symbol,
            timeframe=timeframe,
            source=DrawingSource.DETERMINISTIC,
            confidence=min(95, 72 + int((_impulse_range(start, end) / minimum_range) * 10)),
            label="Fibonacci retracement",
            enabled=True,
            created_at=created_at,
            time_start=start.time,
            time_end=end.time,
            price_low=min(start.price, end.price),
            price_high=max(start.price, end.price),
            anchor_points=[
        ChartPoint(time=start.time, price=start.price),
        ChartPoint(time=end.time, price=end.price),
            ],
            levels=_levels_for_range(start, end),
            style={
                "line_color": "#0f172a",
                "fill_color": "#e2e8f0",
                "text_color": "#334155",
                "line_width": 1,
                "line_style": "dashed",
                "opacity": 0.18,
            },
            state="active",
            metadata={
                "direction": "bullish" if bullish else "bearish",
                "impulse_range": _impulse_range(start, end),
                "category": "fibonacci",
            },
        )
    ]

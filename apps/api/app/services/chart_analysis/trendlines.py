from __future__ import annotations

from datetime import datetime
from statistics import median
from typing import Optional

from app.services.scanner.indicators import atr

from .market_structure import StructureSnapshot, SwingPoint, confirmed_swing_highs, confirmed_swing_lows
from .models import ChartCandle, DrawingSource, RayDrawing, TrendLineDrawing


def _line_price(start: SwingPoint, end: SwingPoint, target_time: datetime) -> float:
    start_ts = start.time.timestamp()
    end_ts = end.time.timestamp()
    if end_ts == start_ts:
        return end.price
    target_ts = target_time.timestamp()
    fraction = (target_ts - start_ts) / (end_ts - start_ts)
    return start.price + (end.price - start.price) * fraction


def _body_crossings(
    candles: list[ChartCandle],
    start: SwingPoint,
    end: SwingPoint,
    tolerance: float,
) -> int:
    crossings = 0
    for candle in candles[start.index + 1 : end.index]:
        price = _line_price(start, end, candle.time)
        body_low = min(candle.open, candle.close)
        body_high = max(candle.open, candle.close)
        if body_low - tolerance <= price <= body_high + tolerance:
            crossings += 1
    return crossings


def _touches(
    candles: list[ChartCandle],
    start: SwingPoint,
    end: SwingPoint,
    tolerance: float,
) -> int:
    touches = 0
    for candle in candles[start.index : end.index + 1]:
        price = _line_price(start, end, candle.time)
        if candle.low - tolerance <= price <= candle.high + tolerance:
            touches += 1
    return touches


def _channel_width(
    candles: list[ChartCandle],
    line_start: SwingPoint,
    line_end: SwingPoint,
    opposite_swings: list[SwingPoint],
) -> Optional[float]:
    if not opposite_swings:
        return None
    distances = []
    for swing in opposite_swings:
        if line_start.index <= swing.index <= line_end.index:
            line_price = _line_price(line_start, line_end, swing.time)
            distances.append(abs(swing.price - line_price))
    if not distances:
        return None
    return median(distances)


def detect_trendlines(
    *,
    symbol: str,
    timeframe: str,
    candles: list[ChartCandle],
    structure: StructureSnapshot,
    created_at: datetime,
) -> list[object]:
    if len(candles) < 10:
        return []

    atr_value = structure.atr or atr([c.model_dump() for c in candles], 14) or (candles[-1].close * 0.001)
    tolerance = max(atr_value * 0.22, candles[-1].close * 0.00025)
    drawings: list[object] = []

    if structure.trend == "uptrend" and len(structure.swing_lows) >= 2:
        lows = structure.swing_lows[-4:]
        candidate_pairs = list(zip(lows, lows[1:]))
        for start, end in reversed(candidate_pairs):
            if end.price <= start.price:
                continue
            touches = _touches(candles, start, end, tolerance)
            body_crossings = _body_crossings(candles, start, end, tolerance)
            if touches < 3 or body_crossings > 2:
                continue
            drawings.append(
                TrendLineDrawing(
                    id=f"{symbol}:{timeframe}:trendline:up:{start.index}:{end.index}",
                    symbol=symbol,
                    timeframe=timeframe,
                    source=DrawingSource.DETERMINISTIC,
                    confidence=min(95, 68 + touches * 6 - body_crossings * 8),
                    label="Uptrend line",
                    enabled=True,
                    created_at=created_at,
                    time_start=start.time,
                    time_end=end.time,
                    price_start=start.price,
                    price_end=end.price,
                    style={
                        "line_color": "#16a34a",
                        "fill_color": None,
                        "text_color": "#14532d",
                        "line_width": 2,
                        "line_style": "solid",
                        "opacity": 0.8,
                    },
                    anchor_points=[
                        {"time": start.time, "price": start.price},
                        {"time": end.time, "price": end.price},
                    ],
                    metadata={
                        "touches": touches,
                        "body_crossings": body_crossings,
                        "channel_width": _channel_width(candles, start, end, structure.swing_highs),
                        "direction": "uptrend",
                        "category": "trendline",
                    },
                )
            )
            if touches >= 4 and body_crossings <= 1:
                drawings.append(
                    RayDrawing(
                        id=f"{symbol}:{timeframe}:ray:up:{start.index}:{end.index}",
                        symbol=symbol,
                        timeframe=timeframe,
                        source=DrawingSource.DETERMINISTIC,
                        confidence=min(95, 66 + touches * 5),
                        label="Uptrend ray",
                        enabled=True,
                        created_at=created_at,
                        time_start=start.time,
                        time_end=candles[-1].time,
                        price_start=start.price,
                        price_end=_line_price(start, end, candles[-1].time),
                        style={
                            "line_color": "#22c55e",
                            "fill_color": None,
                            "text_color": "#14532d",
                            "line_width": 1,
                            "line_style": "dashed",
                            "opacity": 0.65,
                        },
                        anchor_points=[
                            {"time": start.time, "price": start.price},
                            {"time": end.time, "price": end.price},
                        ],
                        metadata={
                            "touches": touches,
                            "body_crossings": body_crossings,
                            "extended_right": True,
                            "category": "trendline_ray",
                        },
                    )
                )
            break

    if structure.trend == "downtrend" and len(structure.swing_highs) >= 2:
        highs = structure.swing_highs[-4:]
        candidate_pairs = list(zip(highs, highs[1:]))
        for start, end in reversed(candidate_pairs):
            if end.price >= start.price:
                continue
            touches = _touches(candles, start, end, tolerance)
            body_crossings = _body_crossings(candles, start, end, tolerance)
            if touches < 3 or body_crossings > 2:
                continue
            drawings.append(
                TrendLineDrawing(
                    id=f"{symbol}:{timeframe}:trendline:down:{start.index}:{end.index}",
                    symbol=symbol,
                    timeframe=timeframe,
                    source=DrawingSource.DETERMINISTIC,
                    confidence=min(95, 68 + touches * 6 - body_crossings * 8),
                    label="Downtrend line",
                    enabled=True,
                    created_at=created_at,
                    time_start=start.time,
                    time_end=end.time,
                    price_start=start.price,
                    price_end=end.price,
                    style={
                        "line_color": "#dc2626",
                        "fill_color": None,
                        "text_color": "#7f1d1d",
                        "line_width": 2,
                        "line_style": "solid",
                        "opacity": 0.8,
                    },
                    anchor_points=[
                        {"time": start.time, "price": start.price},
                        {"time": end.time, "price": end.price},
                    ],
                    metadata={
                        "touches": touches,
                        "body_crossings": body_crossings,
                        "channel_width": _channel_width(candles, start, end, structure.swing_lows),
                        "direction": "downtrend",
                        "category": "trendline",
                    },
                )
            )
            if touches >= 4 and body_crossings <= 1:
                drawings.append(
                    RayDrawing(
                        id=f"{symbol}:{timeframe}:ray:down:{start.index}:{end.index}",
                        symbol=symbol,
                        timeframe=timeframe,
                        source=DrawingSource.DETERMINISTIC,
                        confidence=min(95, 66 + touches * 5),
                        label="Downtrend ray",
                        enabled=True,
                        created_at=created_at,
                        time_start=start.time,
                        time_end=candles[-1].time,
                        price_start=start.price,
                        price_end=_line_price(start, end, candles[-1].time),
                        style={
                            "line_color": "#ef4444",
                            "fill_color": None,
                            "text_color": "#7f1d1d",
                            "line_width": 1,
                            "line_style": "dashed",
                            "opacity": 0.65,
                        },
                        anchor_points=[
                            {"time": start.time, "price": start.price},
                            {"time": end.time, "price": end.price},
                        ],
                        metadata={
                            "touches": touches,
                            "body_crossings": body_crossings,
                            "extended_right": True,
                            "category": "trendline_ray",
                        },
                    )
                )
            break

    return drawings

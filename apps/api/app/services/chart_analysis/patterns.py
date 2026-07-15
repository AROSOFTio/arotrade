from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Optional

from app.services.scanner.indicators import atr

from .market_structure import StructureSnapshot, SwingPoint
from .models import ChartCandle, ChartPoint, DrawingSource, SignalMarkerDrawing, TextLabelDrawing


@dataclass(slots=True)
class PatternDetection:
    name: str
    confidence: int
    confirmed: bool
    neckline: Optional[float]
    breakout_level: Optional[float]
    invalidation_level: Optional[float]
    anchor_points: list[ChartPoint]
    metadata: dict
    direction: str


def _tolerance(candles: list[ChartCandle], structure: StructureSnapshot) -> float:
    atr_value = structure.atr or atr([c.model_dump() for c in candles], 14) or (candles[-1].close * 0.001)
    return max(atr_value * 0.28, candles[-1].close * 0.00025)


def _swings_between(swings: list[SwingPoint], start_index: int, end_index: int, kind: str) -> list[SwingPoint]:
    return [item for item in swings if start_index < item.index < end_index and item.kind == kind]


def _label(
    *,
    symbol: str,
    timeframe: str,
    detection: PatternDetection,
    created_at: datetime,
) -> TextLabelDrawing:
    anchor_time = detection.anchor_points[-1].time if detection.anchor_points else created_at
    anchor_price = detection.anchor_points[-1].price if detection.anchor_points else None
    return TextLabelDrawing(
        id=f"{symbol}:{timeframe}:pattern:{detection.name.replace(' ', '-').lower()}:{int(anchor_time.timestamp())}",
        symbol=symbol,
        timeframe=timeframe,
        source=DrawingSource.DETERMINISTIC,
        confidence=detection.confidence,
        label=detection.name,
        enabled=detection.confidence >= 60,
        created_at=created_at,
        time_start=detection.anchor_points[0].time if detection.anchor_points else created_at,
        time_end=anchor_time,
        price_start=detection.anchor_points[0].price if detection.anchor_points else anchor_price,
        price_end=anchor_price,
        style={
            "line_color": "#0f172a",
            "fill_color": "#ffffff",
            "text_color": "#0f172a",
            "line_width": 0,
            "opacity": 0.0,
        },
        anchor_points=detection.anchor_points,
        state="confirmed" if detection.confirmed else "candidate",
        metadata={
            **detection.metadata,
            "pattern": detection.name,
            "confirmed": detection.confirmed,
            "neckline": detection.neckline,
            "breakout_level": detection.breakout_level,
            "invalidation_level": detection.invalidation_level,
            "direction": detection.direction,
        },
    )


def _marker(
    *,
    symbol: str,
    timeframe: str,
    detection: PatternDetection,
    created_at: datetime,
) -> SignalMarkerDrawing:
    last_anchor = detection.anchor_points[-1]
    return SignalMarkerDrawing(
        id=f"{symbol}:{timeframe}:pattern-marker:{detection.name.replace(' ', '-').lower()}:{int(last_anchor.time.timestamp())}",
        symbol=symbol,
        timeframe=timeframe,
        source=DrawingSource.DETERMINISTIC,
        confidence=detection.confidence,
        label=f"{detection.name} breakout",
        enabled=detection.confirmed,
        created_at=created_at,
        time_start=last_anchor.time,
        time_end=last_anchor.time,
        price_start=detection.breakout_level or last_anchor.price,
        price_end=detection.breakout_level or last_anchor.price,
        style={
            "line_color": "#2563eb" if detection.direction == "bullish" else "#dc2626",
            "fill_color": "#dbeafe" if detection.direction == "bullish" else "#fee2e2",
            "text_color": "#0f172a",
            "line_width": 1,
            "opacity": 0.28,
        },
        anchor_points=detection.anchor_points,
        state="confirmed" if detection.confirmed else "candidate",
        metadata={
            **detection.metadata,
            "pattern": detection.name,
            "confirmed": detection.confirmed,
            "neckline": detection.neckline,
            "breakout_level": detection.breakout_level,
            "invalidation_level": detection.invalidation_level,
        },
    )


def _double_top(
    candles: list[ChartCandle],
    highs: list[SwingPoint],
    lows: list[SwingPoint],
    tolerance: float,
) -> Optional[PatternDetection]:
    if len(highs) < 2:
        return None
    h1, h2 = highs[-2], highs[-1]
    if h2.index - h1.index < 3:
        return None
    if abs(h1.price - h2.price) > tolerance * 1.5:
        return None
    neckline_candidates = _swings_between(lows, h1.index, h2.index, "low")
    neckline = min((item.price for item in neckline_candidates), default=min(c.low for c in candles[h1.index : h2.index + 1]))
    confirmed = candles[-1].close < neckline - tolerance
    invalidation = max(h1.price, h2.price) + tolerance
    confidence = 62 + int((1 - abs(h1.price - h2.price) / max(tolerance, 1e-9)) * 10)
    if confirmed:
        confidence += 10
    if confidence < 60:
        return None
    anchor_points = [
        ChartPoint(time=h1.time, price=h1.price),
        ChartPoint(time=h2.time, price=h2.price),
        ChartPoint(time=candles[-1].time, price=neckline),
    ]
    return PatternDetection(
        name="Double top",
        confidence=min(95, confidence),
        confirmed=confirmed,
        neckline=round(neckline, 6),
        breakout_level=round(neckline, 6) if confirmed else None,
        invalidation_level=round(invalidation, 6),
        anchor_points=anchor_points,
        metadata={"pattern": "double_top", "peak_distance": abs(h1.price - h2.price)},
        direction="bearish",
    )


def _double_bottom(
    candles: list[ChartCandle],
    highs: list[SwingPoint],
    lows: list[SwingPoint],
    tolerance: float,
) -> Optional[PatternDetection]:
    if len(lows) < 2:
        return None
    l1, l2 = lows[-2], lows[-1]
    if l2.index - l1.index < 3:
        return None
    if abs(l1.price - l2.price) > tolerance * 1.5:
        return None
    neckline_candidates = _swings_between(highs, l1.index, l2.index, "high")
    neckline = max((item.price for item in neckline_candidates), default=max(c.high for c in candles[l1.index : l2.index + 1]))
    confirmed = candles[-1].close > neckline + tolerance
    invalidation = min(l1.price, l2.price) - tolerance
    confidence = 62 + int((1 - abs(l1.price - l2.price) / max(tolerance, 1e-9)) * 10)
    if confirmed:
        confidence += 10
    if confidence < 60:
        return None
    anchor_points = [
        ChartPoint(time=l1.time, price=l1.price),
        ChartPoint(time=l2.time, price=l2.price),
        ChartPoint(time=candles[-1].time, price=neckline),
    ]
    return PatternDetection(
        name="Double bottom",
        confidence=min(95, confidence),
        confirmed=confirmed,
        neckline=round(neckline, 6),
        breakout_level=round(neckline, 6) if confirmed else None,
        invalidation_level=round(invalidation, 6),
        anchor_points=anchor_points,
        metadata={"pattern": "double_bottom", "trough_distance": abs(l1.price - l2.price)},
        direction="bullish",
    )


def _ascending_triangle(
    candles: list[ChartCandle],
    highs: list[SwingPoint],
    lows: list[SwingPoint],
    tolerance: float,
) -> Optional[PatternDetection]:
    if len(highs) < 3 or len(lows) < 2:
        return None
    top = highs[-3:]
    if max(item.price for item in top) - min(item.price for item in top) > tolerance * 1.3:
        return None
    low_seq = lows[-3:]
    low_prices = [item.price for item in low_seq]
    if len(low_seq) < 2 or not all(later > earlier for earlier, later in zip(low_prices, low_prices[1:])):
        return None
    neckline = max(item.price for item in top)
    confirmed = candles[-1].close > neckline + tolerance
    invalidation = min(item.price for item in low_seq) - tolerance
    confidence = 61 + int((tolerance * 1.3 - (max(item.price for item in top) - min(item.price for item in top))) / max(tolerance, 1e-9) * 12)
    if confirmed:
        confidence += 8
    if confidence < 60:
        return None
    anchor_points = [ChartPoint(time=item.time, price=item.price) for item in (*top, *low_seq)]
    return PatternDetection(
        name="Ascending triangle",
        confidence=min(95, confidence),
        confirmed=confirmed,
        neckline=round(neckline, 6),
        breakout_level=round(neckline, 6) if confirmed else None,
        invalidation_level=round(invalidation, 6),
        anchor_points=anchor_points,
        metadata={"pattern": "ascending_triangle", "upper_range": [item.price for item in top]},
        direction="bullish",
    )


def _descending_triangle(
    candles: list[ChartCandle],
    highs: list[SwingPoint],
    lows: list[SwingPoint],
    tolerance: float,
) -> Optional[PatternDetection]:
    if len(lows) < 3 or len(highs) < 2:
        return None
    bottom = lows[-3:]
    if max(item.price for item in bottom) - min(item.price for item in bottom) > tolerance * 1.3:
        return None
    high_seq = highs[-3:]
    high_prices = [item.price for item in high_seq]
    if len(high_seq) < 2 or not all(later < earlier for earlier, later in zip(high_prices, high_prices[1:])):
        return None
    neckline = min(item.price for item in bottom)
    confirmed = candles[-1].close < neckline - tolerance
    invalidation = max(item.price for item in high_seq) + tolerance
    confidence = 61 + int((tolerance * 1.3 - (max(item.price for item in bottom) - min(item.price for item in bottom))) / max(tolerance, 1e-9) * 12)
    if confirmed:
        confidence += 8
    if confidence < 60:
        return None
    anchor_points = [ChartPoint(time=item.time, price=item.price) for item in (*bottom, *high_seq)]
    return PatternDetection(
        name="Descending triangle",
        confidence=min(95, confidence),
        confirmed=confirmed,
        neckline=round(neckline, 6),
        breakout_level=round(neckline, 6) if confirmed else None,
        invalidation_level=round(invalidation, 6),
        anchor_points=anchor_points,
        metadata={"pattern": "descending_triangle", "lower_range": [item.price for item in bottom]},
        direction="bearish",
    )


def _symmetrical_triangle(
    candles: list[ChartCandle],
    highs: list[SwingPoint],
    lows: list[SwingPoint],
    tolerance: float,
) -> Optional[PatternDetection]:
    if len(highs) < 3 or len(lows) < 3:
        return None
    upper = highs[-3:]
    lower = lows[-3:]
    upper_prices = [item.price for item in upper]
    lower_prices = [item.price for item in lower]
    if not all(later < earlier for earlier, later in zip(upper_prices, upper_prices[1:])):
        return None
    if not all(later > earlier for earlier, later in zip(lower_prices, lower_prices[1:])):
        return None
    breakout_upper = upper[-1].price
    breakout_lower = lower[-1].price
    confirmed = candles[-1].close > breakout_upper + tolerance or candles[-1].close < breakout_lower - tolerance
    direction = "bullish" if candles[-1].close > breakout_upper else "bearish" if candles[-1].close < breakout_lower else "neutral"
    confidence = 63 + min(12, int((breakout_upper - breakout_lower) / max(tolerance, 1e-9)))
    if confirmed:
        confidence += 6
    if confidence < 60:
        return None
    anchor_points = [ChartPoint(time=item.time, price=item.price) for item in (*upper, *lower)]
    return PatternDetection(
        name="Symmetrical triangle",
        confidence=min(95, confidence),
        confirmed=confirmed,
        neckline=round((breakout_upper + breakout_lower) / 2, 6),
        breakout_level=round(breakout_upper if direction == "bullish" else breakout_lower if direction == "bearish" else (breakout_upper + breakout_lower) / 2, 6),
        invalidation_level=round(breakout_lower - tolerance if direction == "bullish" else breakout_upper + tolerance, 6),
        anchor_points=anchor_points,
        metadata={"pattern": "symmetrical_triangle", "upper": breakout_upper, "lower": breakout_lower},
        direction="bullish" if direction == "bullish" else "bearish" if direction == "bearish" else "neutral",
    )


def _flag_pattern(
    candles: list[ChartCandle],
    structure: StructureSnapshot,
    bullish: bool,
    tolerance: float,
) -> Optional[PatternDetection]:
    if len(candles) < 10:
        return None
    recent = candles[-10:]
    impulse = candles[:-5] if len(candles) > 5 else candles
    if len(impulse) < 5:
        return None
    if bullish:
        if not structure.swing_lows or not structure.swing_highs:
            return None
        impulse_high = structure.swing_highs[-1]
        prior_lows = [item for item in structure.swing_lows if item.index < impulse_high.index]
        if not prior_lows:
            return None
        impulse_low = prior_lows[-1]
        if impulse_high.index - impulse_low.index < 3:
            return None
        if impulse_high.price - impulse_low.price < tolerance * 4:
            return None
        flag_candles = candles[impulse_high.index + 1 :]
        if len(flag_candles) < 3:
            return None
        flag_high = max(item.high for item in flag_candles)
        flag_low = min(item.low for item in flag_candles)
        retracement = impulse_high.price - flag_low
        if retracement > (impulse_high.price - impulse_low.price) * 0.65:
            return None
        confirmed = candles[-1].close > flag_high + tolerance
        confidence = 60 + int((impulse_high.price - impulse_low.price) / max(tolerance, 1e-9))
        if confirmed:
            confidence += 10
        if confidence < 60:
            return None
        anchor_points = [
            ChartPoint(time=impulse_low.time, price=impulse_low.price),
            ChartPoint(time=impulse_high.time, price=impulse_high.price),
            ChartPoint(time=flag_candles[-1].time, price=flag_low),
        ]
        return PatternDetection(
            name="Bull flag",
            confidence=min(95, confidence),
            confirmed=confirmed,
            neckline=round(flag_high, 6),
            breakout_level=round(flag_high, 6) if confirmed else None,
            invalidation_level=round(flag_low - tolerance, 6),
            anchor_points=anchor_points,
            metadata={"pattern": "bull_flag", "impulse_range": impulse_high.price - impulse_low.price},
            direction="bullish",
        )
    if not structure.swing_lows or not structure.swing_highs:
        return None
    impulse_low = structure.swing_lows[-1]
    prior_highs = [item for item in structure.swing_highs if item.index < impulse_low.index]
    if not prior_highs:
        return None
    impulse_high = prior_highs[-1]
    if impulse_low.index - impulse_high.index < 3:
        return None
    if impulse_high.price - impulse_low.price < tolerance * 4:
        return None
    flag_candles = candles[impulse_low.index + 1 :]
    if len(flag_candles) < 3:
        return None
    flag_high = max(item.high for item in flag_candles)
    flag_low = min(item.low for item in flag_candles)
    retracement = flag_high - impulse_low.price
    if retracement > (impulse_high.price - impulse_low.price) * 0.65:
        return None
    confirmed = candles[-1].close < flag_low - tolerance
    confidence = 60 + int((impulse_high.price - impulse_low.price) / max(tolerance, 1e-9))
    if confirmed:
        confidence += 10
    if confidence < 60:
        return None
    anchor_points = [
        ChartPoint(time=impulse_high.time, price=impulse_high.price),
        ChartPoint(time=impulse_low.time, price=impulse_low.price),
        ChartPoint(time=flag_candles[-1].time, price=flag_high),
    ]
    return PatternDetection(
        name="Bear flag",
        confidence=min(95, confidence),
        confirmed=confirmed,
        neckline=round(flag_low, 6),
        breakout_level=round(flag_low, 6) if confirmed else None,
        invalidation_level=round(flag_high + tolerance, 6),
        anchor_points=anchor_points,
        metadata={"pattern": "bear_flag", "impulse_range": impulse_high.price - impulse_low.price},
        direction="bearish",
    )


def _head_and_shoulders(
    candles: list[ChartCandle],
    highs: list[SwingPoint],
    lows: list[SwingPoint],
    tolerance: float,
    inverse: bool = False,
) -> Optional[PatternDetection]:
    if inverse:
        if len(lows) < 3:
            return None
        left, head, right = lows[-3:]
        if not (head.price < left.price and head.price < right.price):
            return None
        if abs(left.price - right.price) > tolerance * 1.6:
            return None
        neckline_candidates = _swings_between(highs, left.index, right.index, "high")
        neckline = max((item.price for item in neckline_candidates), default=max(c.high for c in candles[left.index : right.index + 1]))
        confirmed = candles[-1].close > neckline + tolerance
        invalidation = head.price - tolerance
        confidence = 64 + int((tolerance * 1.6 - abs(left.price - right.price)) / max(tolerance, 1e-9) * 8)
        if confirmed:
            confidence += 10
        if confidence < 60:
            return None
        anchor_points = [ChartPoint(time=item.time, price=item.price) for item in (left, head, right)]
        return PatternDetection(
            name="Inverse head and shoulders",
            confidence=min(95, confidence),
            confirmed=confirmed,
            neckline=round(neckline, 6),
            breakout_level=round(neckline, 6) if confirmed else None,
            invalidation_level=round(invalidation, 6),
            anchor_points=anchor_points,
            metadata={"pattern": "inverse_head_and_shoulders"},
            direction="bullish",
        )

    if len(highs) < 3:
        return None
    left, head, right = highs[-3:]
    if not (head.price > left.price and head.price > right.price):
        return None
    if abs(left.price - right.price) > tolerance * 1.6:
        return None
    neckline_candidates = _swings_between(lows, left.index, right.index, "low")
    neckline = min((item.price for item in neckline_candidates), default=min(c.low for c in candles[left.index : right.index + 1]))
    confirmed = candles[-1].close < neckline - tolerance
    invalidation = head.price + tolerance
    confidence = 64 + int((tolerance * 1.6 - abs(left.price - right.price)) / max(tolerance, 1e-9) * 8)
    if confirmed:
        confidence += 10
    if confidence < 60:
        return None
    anchor_points = [ChartPoint(time=item.time, price=item.price) for item in (left, head, right)]
    return PatternDetection(
        name="Head and shoulders",
        confidence=min(95, confidence),
        confirmed=confirmed,
        neckline=round(neckline, 6),
        breakout_level=round(neckline, 6) if confirmed else None,
        invalidation_level=round(invalidation, 6),
        anchor_points=anchor_points,
        metadata={"pattern": "head_and_shoulders"},
        direction="bearish",
    )


def detect_chart_patterns(
    *,
    symbol: str,
    timeframe: str,
    candles: list[ChartCandle],
    structure: StructureSnapshot,
    created_at: datetime,
) -> list[object]:
    if len(candles) < 12:
        return []

    tolerance = _tolerance(candles, structure)
    highs = structure.swing_highs
    lows = structure.swing_lows

    candidates: list[PatternDetection] = []
    for detector in (
        lambda: _double_top(candles, highs, lows, tolerance),
        lambda: _double_bottom(candles, highs, lows, tolerance),
        lambda: _ascending_triangle(candles, highs, lows, tolerance),
        lambda: _descending_triangle(candles, highs, lows, tolerance),
        lambda: _symmetrical_triangle(candles, highs, lows, tolerance),
        lambda: _flag_pattern(candles, structure, True, tolerance),
        lambda: _flag_pattern(candles, structure, False, tolerance),
        lambda: _head_and_shoulders(candles, highs, lows, tolerance, False),
        lambda: _head_and_shoulders(candles, highs, lows, tolerance, True),
    ):
        result = detector()
        if result and result.confidence >= 60:
            candidates.append(result)

    candidates.sort(key=lambda item: (item.confirmed, item.confidence), reverse=True)
    drawings: list[object] = []
    for detection in candidates[:4]:
        drawings.append(_label(symbol=symbol, timeframe=timeframe, detection=detection, created_at=created_at))
        if detection.confirmed and detection.breakout_level is not None:
            drawings.append(_marker(symbol=symbol, timeframe=timeframe, detection=detection, created_at=created_at))
    return drawings

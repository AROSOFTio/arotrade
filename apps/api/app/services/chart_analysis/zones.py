from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Iterable, Optional

from app.services.scanner.indicators import atr

from .market_structure import (
    StructureEvent,
    StructureSnapshot,
    SwingPoint,
    confirmed_swing_highs,
    confirmed_swing_lows,
    normalize_candles,
    parse_chart_time,
    timeframe_to_seconds,
)
from .models import (
    BaseDrawing,
    ChartCandle,
    DrawingSource,
    FairValueGapDrawing,
    HorizontalLineDrawing,
    LiquidityZoneDrawing,
    OrderBlockDrawing,
    BreakerBlockDrawing,
    RectangleDrawing,
    ResistanceZoneDrawing,
    SupportZoneDrawing,
    SupplyZoneDrawing,
    DemandZoneDrawing,
)


@dataclass(slots=True)
class ZoneState:
    state: str
    touches: int
    first_touch: Optional[datetime]
    latest_touch: Optional[datetime]
    invalidated_at: Optional[datetime]
    invalidated_by_price: Optional[float]
    fill_ratio: float = 0.0


def _price_touch(value: float, low: float, high: float, tolerance: float) -> bool:
    return low - tolerance <= value <= high + tolerance


def _touch_range(candle: ChartCandle, low: float, high: float, tolerance: float) -> bool:
    return candle.high >= low - tolerance and candle.low <= high + tolerance


def _zone_state(
    candles: list[ChartCandle],
    *,
    start_index: int,
    low: float,
    high: float,
    direction: str | None = None,
    tolerance: float = 0.0,
) -> ZoneState:
    touches = 0
    first_touch: Optional[datetime] = None
    latest_touch: Optional[datetime] = None
    invalidated_at: Optional[datetime] = None
    invalidated_by_price: Optional[float] = None
    partial_count = 0

    for candle in candles[start_index + 1 :]:
        touched = _touch_range(candle, low, high, tolerance)
        if not touched:
            continue
        touches += 1
        first_touch = first_touch or candle.time
        latest_touch = candle.time

        if candle.low < low and candle.high > high:
            partial_count += 2
        elif candle.low < low or candle.high > high:
            partial_count += 1

        if direction == "bullish" and candle.close < low - tolerance:
            invalidated_at = candle.time
            invalidated_by_price = candle.close
            break
        if direction == "bearish" and candle.close > high + tolerance:
            invalidated_at = candle.time
            invalidated_by_price = candle.close
            break

    if invalidated_at:
        state = "invalidated"
    elif touches == 0:
        state = "fresh"
    elif touches == 1:
        state = "tested"
    elif partial_count > 0:
        state = "mitigated"
    else:
        state = "active"

    fill_ratio = min(1.0, partial_count / max(1, touches * 2)) if touches else 0.0
    return ZoneState(
        state=state,
        touches=touches,
        first_touch=first_touch,
        latest_touch=latest_touch,
        invalidated_at=invalidated_at,
        invalidated_by_price=invalidated_by_price,
        fill_ratio=fill_ratio,
    )


def _cluster_levels(values: list[tuple[float, datetime]], tolerance: float) -> list[list[tuple[float, datetime]]]:
    if not values:
        return []
    ordered = sorted(values, key=lambda item: item[0])
    clusters: list[list[tuple[float, datetime]]] = [[ordered[0]]]
    for price, time in ordered[1:]:
        cluster = clusters[-1]
        center = sum(item[0] for item in cluster) / len(cluster)
        if abs(price - center) <= tolerance:
            cluster.append((price, time))
        else:
            clusters.append([(price, time)])
    return clusters


def _zone_bounds(prices: list[float], tolerance: float) -> tuple[float, float]:
    center = sum(prices) / len(prices)
    spread = max(prices) - min(prices)
    band = max(spread * 0.5, tolerance * 0.35)
    return round(center - band, 6), round(center + band, 6)


def _score_zone(*, touches: int, recency_seconds: float, strength: float, invalidated: bool = False) -> int:
    score = touches * 14 + int(strength * 8)
    if recency_seconds < 3600:
        score += 16
    elif recency_seconds < 86400:
        score += 8
    if invalidated:
        score -= 30
    return max(0, min(100, score))


def detect_support_resistance_zones(
    *,
    symbol: str,
    timeframe: str,
    candles: list[ChartCandle],
    structure: StructureSnapshot,
    created_at: datetime,
    max_visible: int = 8,
) -> list[BaseDrawing]:
    if not candles:
        return []
    current_price = structure.current_price or candles[-1].close
    atr_value = structure.atr or atr([c.model_dump() for c in candles], 14) or (current_price * 0.001)
    tolerance = max(atr_value * 0.35, current_price * 0.0003)

    swing_highs = [
        (item.price, item.time, item.strength)
        for item in structure.swing_highs
    ]
    swing_lows = [
        (item.price, item.time, item.strength)
        for item in structure.swing_lows
    ]

    def _build(
        items: list[tuple[float, datetime, float]],
        *,
        drawing_type: str,
        label_prefix: str,
    ) -> list[BaseDrawing]:
        grouped = _cluster_levels([(price, time) for price, time, _ in items], tolerance)
        drawings: list[BaseDrawing] = []
        for cluster in grouped:
            prices = [price for price, _ in cluster]
            times = [time for _, time in cluster]
            if not prices:
                continue
            low, high = _zone_bounds(prices, tolerance)
            center = (low + high) / 2
            touches = 0
            strength = 0.0
            first_touch: Optional[datetime] = None
            latest_touch: Optional[datetime] = None
            for price, time, swing_strength in items:
                if _price_touch(price, low, high, tolerance):
                    touches += 1
                    strength += swing_strength
                    first_touch = first_touch or time
                    latest_touch = time
            zone_state = _zone_state(candles, start_index=0, low=low, high=high, tolerance=tolerance)
            invalidated = zone_state.state == "invalidated"
            recency_seconds = (
                (candles[-1].time - latest_touch).total_seconds()
                if latest_touch
                else float("inf")
            )
            score = _score_zone(
                touches=touches,
                recency_seconds=recency_seconds,
                strength=strength,
                invalidated=invalidated,
            )
            drawings.append(
                {
                    "drawing_type": drawing_type,
                    "score": score,
                    "center": center,
                    "low": low,
                    "high": high,
                    "touches": touches,
                    "first_touch": first_touch,
                    "latest_touch": latest_touch,
                    "state": zone_state.state,
                }
            )
        drawings.sort(key=lambda item: (item["score"], item["touches"]), reverse=True)
        return drawings[:max_visible]

    support_candidates = _build(swing_lows, drawing_type="support_zone", label_prefix="Support")
    resistance_candidates = _build(swing_highs, drawing_type="resistance_zone", label_prefix="Resistance")
    drawings: list[BaseDrawing] = []

    for candidate in support_candidates:
        drawings.append(
            SupportZoneDrawing(
                id=f"{symbol}:{timeframe}:support:{candidate['center']:.5f}:{candidate['touches']}",
                symbol=symbol,
                timeframe=timeframe,
                source=DrawingSource.DETERMINISTIC,
                confidence=candidate["score"],
                label="Support zone",
                enabled=candidate["state"] != "invalidated",
                created_at=created_at,
                time_start=candidate["first_touch"] or candles[0].time,
                time_end=candidate["latest_touch"] or candles[-1].time,
                price_low=candidate["low"],
                price_high=candidate["high"],
                style={
                    "line_color": "#16a34a",
                    "fill_color": "#bbf7d0",
                    "text_color": "#14532d",
                    "line_width": 1,
                    "opacity": 0.18,
                },
                state=candidate["state"],
                metadata={
                    "touches": candidate["touches"],
                    "center": candidate["center"],
                    "category": "support",
                    "strength": candidate["score"],
                },
                invalidation=(
                    {
                        "status": candidate["state"],
                        "reason": "Support level failed",
                        "invalidated_at": candidate["latest_touch"],
                        "invalidated_by_price": candidate["high"],
                    }
                    if candidate["state"] == "invalidated"
                    else None
                ),
            )
        )

    for candidate in resistance_candidates:
        drawings.append(
            ResistanceZoneDrawing(
                id=f"{symbol}:{timeframe}:resistance:{candidate['center']:.5f}:{candidate['touches']}",
                symbol=symbol,
                timeframe=timeframe,
                source=DrawingSource.DETERMINISTIC,
                confidence=candidate["score"],
                label="Resistance zone",
                enabled=candidate["state"] != "invalidated",
                created_at=created_at,
                time_start=candidate["first_touch"] or candles[0].time,
                time_end=candidate["latest_touch"] or candles[-1].time,
                price_low=candidate["low"],
                price_high=candidate["high"],
                style={
                    "line_color": "#dc2626",
                    "fill_color": "#fecaca",
                    "text_color": "#7f1d1d",
                    "line_width": 1,
                    "opacity": 0.18,
                },
                state=candidate["state"],
                metadata={
                    "touches": candidate["touches"],
                    "center": candidate["center"],
                    "category": "resistance",
                    "strength": candidate["score"],
                },
                invalidation=(
                    {
                        "status": candidate["state"],
                        "reason": "Resistance failed",
                        "invalidated_at": candidate["latest_touch"],
                        "invalidated_by_price": candidate["low"],
                    }
                    if candidate["state"] == "invalidated"
                    else None
                ),
            )
        )

    return drawings

def detect_fair_value_gaps(
    *,
    symbol: str,
    timeframe: str,
    candles: list[ChartCandle],
    created_at: datetime,
    max_visible: int = 12,
) -> list[FairValueGapDrawing]:
    drawings: list[FairValueGapDrawing] = []
    if len(candles) < 3:
        return drawings

    for index in range(2, len(candles)):
        first = candles[index - 2]
        middle = candles[index - 1]
        third = candles[index]

        bullish = third.low > first.high
        bearish = third.high < first.low
        if not bullish and not bearish:
            continue

        price_low = first.high if bullish else third.high
        price_high = third.low if bullish else first.low
        state = "open"
        fill_ratio = 0.0
        invalidated_at: Optional[datetime] = None
        invalidated_by_price: Optional[float] = None
        touched = False

        for later in candles[index + 1 :]:
            if bullish:
                if later.low <= price_low and later.high >= price_high:
                    state = "filled"
                    fill_ratio = 1.0
                    touched = True
                    break
                if later.low <= price_high and later.high >= price_low:
                    touched = True
                    fill_ratio = max(fill_ratio, 0.5)
                if later.close < price_low:
                    state = "invalidated"
                    invalidated_at = later.time
                    invalidated_by_price = later.close
                    break
            else:
                if later.high >= price_high and later.low <= price_low:
                    state = "filled"
                    fill_ratio = 1.0
                    touched = True
                    break
                if later.high >= price_low and later.low <= price_high:
                    touched = True
                    fill_ratio = max(fill_ratio, 0.5)
                if later.close > price_high:
                    state = "invalidated"
                    invalidated_at = later.time
                    invalidated_by_price = later.close
                    break

        if state == "open" and touched:
            state = "partial"
            fill_ratio = max(fill_ratio, 0.35)
        enabled = state in {"open", "partial"}
        confidence = 88 if state == "open" else 72 if state == "partial" else 45

        drawings.append(
            FairValueGapDrawing(
                id=f"{symbol}:{timeframe}:fvg:{index}:{'bull' if bullish else 'bear'}",
                symbol=symbol,
                timeframe=timeframe,
                source=DrawingSource.DETERMINISTIC,
                confidence=confidence,
                label="Bullish FVG" if bullish else "Bearish FVG",
                enabled=enabled,
                created_at=created_at,
                time_start=first.time,
                time_end=third.time,
                price_low=price_low,
                price_high=price_high,
                style={
                    "line_color": "#2563eb" if bullish else "#dc2626",
                    "fill_color": "#dbeafe" if bullish else "#fee2e2",
                    "text_color": "#0f172a",
                    "line_width": 1,
                    "opacity": 0.22,
                },
                state=state,
                metadata={
                    "direction": "bullish" if bullish else "bearish",
                    "fill_ratio": fill_ratio,
                    "middle_candle_time": middle.time.isoformat(),
                },
                invalidation=(
                    {
                        "status": "invalidated",
                        "reason": "Price closed through the far side of the gap",
                        "invalidated_at": invalidated_at,
                        "invalidated_by_price": invalidated_by_price,
                    }
                    if state == "invalidated"
                    else (
                        {
                            "status": "filled",
                            "reason": "Gap fully filled by later price action",
                            "invalidated_at": candles[-1].time,
                            "invalidated_by_price": candles[-1].close,
                        }
                        if state == "filled"
                        else None
                    )
                ),
            )
        )

    drawings.sort(key=lambda item: (item.enabled, item.confidence, item.created_at), reverse=True)
    return drawings[:max_visible]


def detect_liquidity_zones(
    *,
    symbol: str,
    timeframe: str,
    candles: list[ChartCandle],
    structure: StructureSnapshot,
    created_at: datetime,
) -> list[LiquidityZoneDrawing]:
    if not candles:
        return []

    current_price = structure.current_price or candles[-1].close
    atr_value = structure.atr or atr([c.model_dump() for c in candles], 14) or (current_price * 0.001)
    tolerance = max(atr_value * 0.25, current_price * 0.00025)
    drawings: list[LiquidityZoneDrawing] = []

    def _cluster_drawings(swings: list[SwingPoint], side: str) -> list[LiquidityZoneDrawing]:
        if not swings:
            return []
        clusters: list[list[SwingPoint]] = []
        ordered = sorted(swings, key=lambda item: item.price)
        clusters.append([ordered[0]])
        for swing in ordered[1:]:
            center = sum(item.price for item in clusters[-1]) / len(clusters[-1])
            if abs(swing.price - center) <= tolerance:
                clusters[-1].append(swing)
            else:
                clusters.append([swing])
        result: list[LiquidityZoneDrawing] = []
        for cluster in clusters:
            if len(cluster) < 2:
                continue
            low = min(item.price for item in cluster)
            high = max(item.price for item in cluster)
            first_time = min(item.time for item in cluster)
            latest_time = max(item.time for item in cluster)
            state = "resting"
            if side == "high":
                swept = any(candle.high > high + tolerance and candle.close < high for candle in candles if candle.time >= latest_time)
            else:
                swept = any(candle.low < low - tolerance and candle.close > low for candle in candles if candle.time >= latest_time)
            if swept:
                state = "swept"
            result.append(
                LiquidityZoneDrawing(
                    id=f"{symbol}:{timeframe}:liquidity:{side}:{low:.5f}:{high:.5f}",
                    symbol=symbol,
                    timeframe=timeframe,
                    source=DrawingSource.DETERMINISTIC,
                    confidence=min(95, 55 + len(cluster) * 8),
                    label="Equal highs liquidity" if side == "high" else "Equal lows liquidity",
                    enabled=state != "invalidated",
                    created_at=created_at,
                    time_start=first_time,
                    time_end=latest_time,
                    price_low=low,
                    price_high=high,
                    style={
                        "line_color": "#0ea5e9" if side == "high" else "#10b981",
                        "fill_color": "#e0f2fe" if side == "high" else "#d1fae5",
                        "text_color": "#0f172a",
                        "line_width": 1,
                        "opacity": 0.18,
                    },
                    state=state,
                    metadata={
                        "cluster_size": len(cluster),
                        "category": "equal_highs" if side == "high" else "equal_lows",
                        "tolerance": tolerance,
                    },
                )
            )
        return result

    drawings.extend(_cluster_drawings(structure.swing_highs, "high"))
    drawings.extend(_cluster_drawings(structure.swing_lows, "low"))

    # Previous day high/low where enough data exists.
    by_date: dict[datetime.date, list[ChartCandle]] = defaultdict(list)
    for candle in candles:
        by_date[candle.time.date()].append(candle)
    dates = sorted(by_date)
    if len(dates) >= 2:
        prev_day = dates[-2]
        prev_candles = by_date[prev_day]
        prev_high = max(candle.high for candle in prev_candles)
        prev_low = min(candle.low for candle in prev_candles)
        prev_time = max(candle.time for candle in prev_candles)
        last_time = candles[-1].time
        high_swept = any(candle.high > prev_high + tolerance and candle.close < prev_high for candle in candles if candle.time > prev_time)
        low_swept = any(candle.low < prev_low - tolerance and candle.close > prev_low for candle in candles if candle.time > prev_time)
        drawings.append(
            LiquidityZoneDrawing(
                id=f"{symbol}:{timeframe}:previous-day-high:{prev_day.isoformat()}",
                symbol=symbol,
                timeframe=timeframe,
                source=DrawingSource.DETERMINISTIC,
                confidence=82,
                label="Previous day high",
                enabled=not high_swept,
                created_at=created_at,
                time_start=prev_candles[0].time,
                time_end=last_time,
                price_low=prev_high - tolerance * 0.15,
                price_high=prev_high + tolerance * 0.15,
                style={
                    "line_color": "#6366f1",
                    "fill_color": "#e0e7ff",
                    "text_color": "#312e81",
                    "line_width": 1,
                    "opacity": 0.16,
                },
                state="swept" if high_swept else "resting",
                metadata={"category": "previous_day_high"},
            )
        )
        drawings.append(
            LiquidityZoneDrawing(
                id=f"{symbol}:{timeframe}:previous-day-low:{prev_day.isoformat()}",
                symbol=symbol,
                timeframe=timeframe,
                source=DrawingSource.DETERMINISTIC,
                confidence=82,
                label="Previous day low",
                enabled=not low_swept,
                created_at=created_at,
                time_start=prev_candles[0].time,
                time_end=last_time,
                price_low=prev_low - tolerance * 0.15,
                price_high=prev_low + tolerance * 0.15,
                style={
                    "line_color": "#8b5cf6",
                    "fill_color": "#ede9fe",
                    "text_color": "#4c1d95",
                    "line_width": 1,
                    "opacity": 0.16,
                },
                state="swept" if low_swept else "resting",
                metadata={"category": "previous_day_low"},
            )
        )

    return drawings


def _last_bos_events(structure: StructureSnapshot) -> list[StructureEvent]:
    return [event for event in structure.events if event.kind == "BOS"]


def _zone_from_range(
    *,
    candles: list[ChartCandle],
    start_index: int,
    end_index: int,
    bullish: bool,
) -> tuple[float, float]:
    base = candles[start_index : end_index + 1]
    if not base:
        return candles[start_index].low, candles[end_index].high
    lows = [c.low for c in base]
    highs = [c.high for c in base]
    opens = [c.open for c in base]
    closes = [c.close for c in base]
    if bullish:
        return min(lows), max(max(opens), max(closes), max(highs))
    return min(min(opens), min(closes), min(lows)), max(highs)


def _build_zone_drawing(
    *,
    drawing_cls,
    symbol: str,
    timeframe: str,
    created_at: datetime,
    candles: list[ChartCandle],
    zone_id: str,
    label: str,
    bullish: bool,
    low: float,
    high: float,
    start_time: datetime,
    end_time: datetime,
    score: int,
    state: str,
    metadata: dict,
) -> BaseDrawing:
    return drawing_cls(
        id=zone_id,
        symbol=symbol,
        timeframe=timeframe,
        source=DrawingSource.DETERMINISTIC,
        confidence=score,
        label=label,
        enabled=state != "invalidated",
        created_at=created_at,
        time_start=start_time,
        time_end=end_time,
        price_low=low,
        price_high=high,
        style={
            "line_color": "#16a34a" if bullish else "#dc2626",
            "fill_color": "#dcfce7" if bullish else "#fee2e2",
            "text_color": "#0f172a",
            "line_width": 1,
            "opacity": 0.2,
        },
        state=state,
        metadata=metadata,
    )


def detect_supply_demand_zones(
    *,
    symbol: str,
    timeframe: str,
    candles: list[ChartCandle],
    structure: StructureSnapshot,
    created_at: datetime,
) -> list[BaseDrawing]:
    drawings: list[BaseDrawing] = []
    if len(candles) < 8:
        return drawings

    atr_value = structure.atr or atr([c.model_dump() for c in candles], 14) or (candles[-1].close * 0.001)
    impulse_threshold = atr_value * 1.25
    base_threshold = atr_value * 0.65

    for index in range(3, len(candles)):
        displacement = candles[index]
        body = abs(displacement.close - displacement.open)
        range_size = displacement.high - displacement.low
        if body < impulse_threshold or range_size < impulse_threshold * 1.15:
            continue

        base_start = max(0, index - 3)
        base = candles[base_start:index]
        if len(base) < 2:
            continue
        avg_base_body = sum(abs(c.close - c.open) for c in base) / len(base)
        avg_base_range = sum(c.high - c.low for c in base) / len(base)
        if avg_base_body > base_threshold or avg_base_range > atr_value:
            continue

        previous_high = max(c.high for c in candles[:base_start]) if base_start > 0 else base[0].high
        previous_low = min(c.low for c in candles[:base_start]) if base_start > 0 else base[0].low
        bullish = displacement.close > displacement.open and displacement.close > previous_high + atr_value * 0.15
        bearish = displacement.close < displacement.open and displacement.close < previous_low - atr_value * 0.15
        if not bullish and not bearish:
            continue

        zone_low = min(c.low for c in base)
        zone_high = max(c.high for c in base)
        touches = sum(1 for candle in candles[index + 1 :] if _touch_range(candle, zone_low, zone_high, atr_value * 0.08))
        state = "fresh" if touches == 0 else "tested" if touches == 1 else "mitigated"
        if bullish:
            invalidated = any(candle.close < zone_low - atr_value * 0.1 for candle in candles[index + 1 :])
            if invalidated:
                state = "invalidated"
            drawings.append(
                _build_zone_drawing(
                    drawing_cls=DemandZoneDrawing,
                    symbol=symbol,
                    timeframe=timeframe,
                    created_at=created_at,
                    candles=candles,
                    zone_id=f"{symbol}:{timeframe}:demand:{index}",
                    label="Demand zone",
                    bullish=True,
                    low=zone_low,
                    high=zone_high,
                    start_time=base[0].time,
                    end_time=displacement.time,
                    score=min(100, 65 + touches * 10 + int((body / atr_value) * 8)),
                    state=state,
                    metadata={
                        "displacement_index": index,
                        "base_start": base_start,
                        "base_end": index - 1,
                        "touches": touches,
                        "impulse_body": body,
                        "category": "demand",
                    },
                )
            )
        else:
            invalidated = any(candle.close > zone_high + atr_value * 0.1 for candle in candles[index + 1 :])
            if invalidated:
                state = "invalidated"
            drawings.append(
                _build_zone_drawing(
                    drawing_cls=SupplyZoneDrawing,
                    symbol=symbol,
                    timeframe=timeframe,
                    created_at=created_at,
                    candles=candles,
                    zone_id=f"{symbol}:{timeframe}:supply:{index}",
                    label="Supply zone",
                    bullish=False,
                    low=zone_low,
                    high=zone_high,
                    start_time=base[0].time,
                    end_time=displacement.time,
                    score=min(100, 65 + touches * 10 + int((body / atr_value) * 8)),
                    state=state,
                    metadata={
                        "displacement_index": index,
                        "base_start": base_start,
                        "base_end": index - 1,
                        "touches": touches,
                        "impulse_body": body,
                        "category": "supply",
                    },
                )
            )

    return drawings


def detect_order_blocks(
    *,
    symbol: str,
    timeframe: str,
    candles: list[ChartCandle],
    structure: StructureSnapshot,
    created_at: datetime,
) -> list[BaseDrawing]:
    drawings: list[BaseDrawing] = []
    if len(candles) < 10:
        return drawings

    atr_value = structure.atr or atr([c.model_dump() for c in candles], 14) or (candles[-1].close * 0.001)
    bos_events = _last_bos_events(structure)
    if not bos_events:
        return drawings

    for event in bos_events:
        direction = event.direction
        event_idx = next((i for i, candle in enumerate(candles) if candle.time == event.time), len(candles) - 1)
        if direction == "bullish":
            base_idx = None
            for candidate in range(event_idx - 1, max(1, event_idx - 4), -1):
                candle = candles[candidate]
                if candle.close < candle.open:
                    base_idx = candidate
                    break
            if base_idx is None:
                continue
            displacement = candles[event_idx]
            body = abs(displacement.close - displacement.open)
            if body < atr_value * 1.1:
                continue
            zone_low, zone_high = _zone_from_range(candles=candles, start_index=base_idx, end_index=base_idx, bullish=True)
            state_result = _zone_state(candles, start_index=base_idx, low=zone_low, high=zone_high, direction="bullish", tolerance=atr_value * 0.08)
            state = state_result.state
            drawings.append(
                _build_zone_drawing(
                    drawing_cls=OrderBlockDrawing,
                    symbol=symbol,
                    timeframe=timeframe,
                    created_at=created_at,
                    candles=candles,
                    zone_id=f"{symbol}:{timeframe}:order-block:bull:{base_idx}:{event_idx}",
                    label="Bullish order block",
                    bullish=True,
                    low=zone_low,
                    high=zone_high,
                    start_time=candles[base_idx].time,
                    end_time=displacement.time,
                    score=min(100, 70 + int((body / atr_value) * 10) + state_result.touches * 5),
                    state=state,
                    metadata={
                        "bos_time": event.time.isoformat(),
                        "displacement_index": event_idx,
                        "base_index": base_idx,
                        "structure_event": event.kind,
                        "category": "order_block",
                    },
                )
            )
            if state == "invalidated" and event_idx + 2 < len(candles):
                for later_idx in range(event_idx + 1, len(candles)):
                    later = candles[later_idx]
                    if later.close < candles[base_idx].low - atr_value * 0.08:
                        drawings.append(
                            _build_zone_drawing(
                                drawing_cls=BreakerBlockDrawing,
                                symbol=symbol,
                                timeframe=timeframe,
                                created_at=created_at,
                                candles=candles,
                                zone_id=f"{symbol}:{timeframe}:breaker-block:bull:{base_idx}:{later_idx}",
                                label="Bullish breaker block",
                                bullish=False,
                                low=zone_low,
                                high=zone_high,
                                start_time=candles[base_idx].time,
                                end_time=later.time,
                                score=min(100, 58 + int((body / atr_value) * 8)),
                                state="active",
                                metadata={
                                    "original_order_block": f"{symbol}:{timeframe}:order-block:bull:{base_idx}:{event_idx}",
                                    "invalidation_time": later.time.isoformat(),
                                    "category": "breaker_block",
                                    "reclaimed_direction": "bearish",
                                },
                            )
                        )
                        break
        else:
            base_idx = None
            for candidate in range(event_idx - 1, max(1, event_idx - 4), -1):
                candle = candles[candidate]
                if candle.close > candle.open:
                    base_idx = candidate
                    break
            if base_idx is None:
                continue
            displacement = candles[event_idx]
            body = abs(displacement.close - displacement.open)
            if body < atr_value * 1.1:
                continue
            zone_low, zone_high = _zone_from_range(candles=candles, start_index=base_idx, end_index=base_idx, bullish=False)
            state_result = _zone_state(candles, start_index=base_idx, low=zone_low, high=zone_high, direction="bearish", tolerance=atr_value * 0.08)
            state = state_result.state
            drawings.append(
                _build_zone_drawing(
                    drawing_cls=OrderBlockDrawing,
                    symbol=symbol,
                    timeframe=timeframe,
                    created_at=created_at,
                    candles=candles,
                    zone_id=f"{symbol}:{timeframe}:order-block:bear:{base_idx}:{event_idx}",
                    label="Bearish order block",
                    bullish=False,
                    low=zone_low,
                    high=zone_high,
                    start_time=candles[base_idx].time,
                    end_time=displacement.time,
                    score=min(100, 70 + int((body / atr_value) * 10) + state_result.touches * 5),
                    state=state,
                    metadata={
                        "bos_time": event.time.isoformat(),
                        "displacement_index": event_idx,
                        "base_index": base_idx,
                        "structure_event": event.kind,
                        "category": "order_block",
                    },
                )
            )
            if state == "invalidated" and event_idx + 2 < len(candles):
                for later_idx in range(event_idx + 1, len(candles)):
                    later = candles[later_idx]
                    if later.close > candles[base_idx].high + atr_value * 0.08:
                        drawings.append(
                            _build_zone_drawing(
                                drawing_cls=BreakerBlockDrawing,
                                symbol=symbol,
                                timeframe=timeframe,
                                created_at=created_at,
                                candles=candles,
                                zone_id=f"{symbol}:{timeframe}:breaker-block:bear:{base_idx}:{later_idx}",
                                label="Bearish breaker block",
                                bullish=True,
                                low=zone_low,
                                high=zone_high,
                                start_time=candles[base_idx].time,
                                end_time=later.time,
                                score=min(100, 58 + int((body / atr_value) * 8)),
                                state="active",
                                metadata={
                                    "original_order_block": f"{symbol}:{timeframe}:order-block:bear:{base_idx}:{event_idx}",
                                    "invalidation_time": later.time.isoformat(),
                                    "category": "breaker_block",
                                    "reclaimed_direction": "bullish",
                                },
                            )
                        )
                        break

    return drawings

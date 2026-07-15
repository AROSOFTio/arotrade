from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from app.services.scanner.indicators import atr, ema, macd, rsi

from .market_structure import StructureSnapshot, confirmed_swing_highs, confirmed_swing_lows
from .models import (
    BaseDrawing,
    ChartCandle,
    ChartPoint,
    DrawingSource,
    EntryZoneDrawing,
    ExplanationSummary,
    HorizontalLineDrawing,
    RiskRewardBoxDrawing,
    SignalMarkerDrawing,
    SignalSummary,
    StopLossDrawing,
    TakeProfitDrawing,
    TextLabelDrawing,
)


@dataclass(slots=True)
class SignalPackage:
    signal: SignalSummary
    drawings: list[BaseDrawing]


def _is_active(drawing: object) -> bool:
    enabled = getattr(drawing, "enabled", False)
    state = str(getattr(drawing, "state", "") or "").lower()
    return bool(enabled) and state not in {"invalidated", "filled", "expired"}


def _midpoint(drawing: object) -> Optional[float]:
    low = getattr(drawing, "price_low", None)
    high = getattr(drawing, "price_high", None)
    if low is None or high is None:
        return None
    return (float(low) + float(high)) / 2.0


def _zone_bounds(drawing: object) -> tuple[Optional[float], Optional[float]]:
    low = getattr(drawing, "price_low", None)
    high = getattr(drawing, "price_high", None)
    if low is None or high is None:
        return None, None
    return float(low), float(high)


def _nearest_zone(
    drawings: Iterable[object],
    *,
    current_price: float,
    bullish: bool,
) -> Optional[object]:
    candidates = []
    for drawing in drawings:
        if not _is_active(drawing):
            continue
        midpoint = _midpoint(drawing)
        if midpoint is None:
            continue
        low, high = _zone_bounds(drawing)
        if low is None or high is None:
            continue
        if bullish and high > current_price * 1.015:
            continue
        if not bullish and low < current_price * 0.985:
            continue
        distance = abs(current_price - midpoint)
        candidates.append((distance, -getattr(drawing, "confidence", 0), drawing))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def _nearest_target_zone(
    drawings: Iterable[object],
    *,
    current_price: float,
    bullish: bool,
) -> Optional[object]:
    candidates = []
    for drawing in drawings:
        if not _is_active(drawing):
            continue
        midpoint = _midpoint(drawing)
        if midpoint is None:
            continue
        low, high = _zone_bounds(drawing)
        if low is None or high is None:
            continue
        if bullish and midpoint <= current_price:
            continue
        if not bullish and midpoint >= current_price:
            continue
        distance = abs(midpoint - current_price)
        candidates.append((distance, -getattr(drawing, "confidence", 0), drawing))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def _indicator_score(
    *,
    bias: str,
    trend: str,
    structure: str,
    ema20: Optional[float],
    ema50: Optional[float],
    ema200: Optional[float],
    rsi14: Optional[float],
    macd_histogram: Optional[float],
    bullish: bool,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if bullish:
        if bias == "bullish":
            score += 2
            reasons.append("Higher-timeframe bias is bullish.")
        if trend == "uptrend":
            score += 2
            reasons.append("Price structure is in an uptrend.")
        if structure == "bullish":
            score += 2
            reasons.append("Swing highs and lows are making higher highs and higher lows.")
        if ema20 is not None and ema50 is not None and ema20 > ema50:
            score += 1
            reasons.append("EMA20 is above EMA50.")
        if ema50 is not None and ema200 is not None and ema50 > ema200:
            score += 1
            reasons.append("EMA50 is above EMA200.")
        if rsi14 is not None and rsi14 >= 50:
            score += 1
            reasons.append(f"RSI14 is {rsi14:.1f}, which supports bullish momentum.")
        if macd_histogram is not None and macd_histogram > 0:
            score += 1
            reasons.append("MACD histogram is positive.")
    else:
        if bias == "bearish":
            score += 2
            reasons.append("Higher-timeframe bias is bearish.")
        if trend == "downtrend":
            score += 2
            reasons.append("Price structure is in a downtrend.")
        if structure == "bearish":
            score += 2
            reasons.append("Swing highs and lows are making lower highs and lower lows.")
        if ema20 is not None and ema50 is not None and ema20 < ema50:
            score += 1
            reasons.append("EMA20 is below EMA50.")
        if ema50 is not None and ema200 is not None and ema50 < ema200:
            score += 1
            reasons.append("EMA50 is below EMA200.")
        if rsi14 is not None and rsi14 <= 50:
            score += 1
            reasons.append(f"RSI14 is {rsi14:.1f}, which supports bearish momentum.")
        if macd_histogram is not None and macd_histogram < 0:
            score += 1
            reasons.append("MACD histogram is negative.")
    return score, reasons


def derive_signal(
    *,
    symbol: str,
    timeframe: str,
    candles: list[ChartCandle],
    structure: StructureSnapshot,
    drawings: list[object],
    created_at: datetime,
) -> SignalPackage:
    if not candles:
        return SignalPackage(
            signal=SignalSummary(action="AVOID", confidence=0, warnings=["No candles available for analysis."]),
            drawings=[],
        )

    current_price = structure.current_price or candles[-1].close
    atr_value = structure.atr or atr([c.model_dump() for c in candles], 14) or (current_price * 0.001)
    closes = [candle.close for candle in candles]
    ema20 = structure.ema20
    ema50 = structure.ema50
    ema200 = structure.ema200
    rsi14 = structure.rsi14
    macd_histogram = structure.macd_histogram

    active_supports = [d for d in drawings if getattr(d, "type", "") in {"support_zone", "demand_zone", "order_block", "breaker_block"}]
    active_resistances = [d for d in drawings if getattr(d, "type", "") in {"resistance_zone", "supply_zone", "order_block", "breaker_block"}]
    active_fvg = [d for d in drawings if getattr(d, "type", "") == "fair_value_gap"]
    active_patterns = [d for d in drawings if getattr(d, "type", "") in {"text_label", "signal_marker"} and "pattern" in (getattr(d, "metadata", {}) or {})]

    bullish_score, bullish_reasons = _indicator_score(
        bias=structure.bias,
        trend=structure.trend,
        structure=structure.structure,
        ema20=ema20,
        ema50=ema50,
        ema200=ema200,
        rsi14=rsi14,
        macd_histogram=macd_histogram,
        bullish=True,
    )
    bearish_score, bearish_reasons = _indicator_score(
        bias=structure.bias,
        trend=structure.trend,
        structure=structure.structure,
        ema20=ema20,
        ema50=ema50,
        ema200=ema200,
        rsi14=rsi14,
        macd_histogram=macd_histogram,
        bullish=False,
    )

    if any(event.kind == "CHOCH" for event in structure.events):
        bullish_score += 1
        bearish_score += 1

    bullish_zone = _nearest_zone(active_supports + [d for d in active_fvg if getattr(d, "metadata", {}).get("direction") == "bullish"], current_price=current_price, bullish=True)
    bearish_zone = _nearest_zone(active_resistances + [d for d in active_fvg if getattr(d, "metadata", {}).get("direction") == "bearish"], current_price=current_price, bullish=False)

    if bullish_zone:
        bullish_score += 2
        bullish_reasons.append(
            f"Nearest bullish zone is {getattr(bullish_zone, 'label', 'unknown')} around {(_midpoint(bullish_zone) or current_price):.5f}."
        )
    if bearish_zone:
        bearish_score += 2
        bearish_reasons.append(
            f"Nearest bearish zone is {getattr(bearish_zone, 'label', 'unknown')} around {(_midpoint(bearish_zone) or current_price):.5f}."
        )

    if any(getattr(item, "confirmed", False) and getattr(item, "direction", "") == "bullish" for item in active_patterns):
        bullish_score += 2
        bullish_reasons.append("A bullish chart pattern is confirmed.")
    if any(getattr(item, "confirmed", False) and getattr(item, "direction", "") == "bearish" for item in active_patterns):
        bearish_score += 2
        bearish_reasons.append("A bearish chart pattern is confirmed.")

    if bullish_score - bearish_score >= 3 and bullish_score >= 6 and bullish_zone is not None:
        return _build_trade_signal(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            structure=structure,
            created_at=created_at,
            bullish=True,
            entry_zone=bullish_zone,
            opposing_zone=bearish_zone,
            score=bullish_score,
            reasons=bullish_reasons,
            warnings=[],
        )

    if bearish_score - bullish_score >= 3 and bearish_score >= 6 and bearish_zone is not None:
        return _build_trade_signal(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            structure=structure,
            created_at=created_at,
            bullish=False,
            entry_zone=bearish_zone,
            opposing_zone=bullish_zone,
            score=bearish_score,
            reasons=bearish_reasons,
            warnings=[],
        )

    if bullish_score == bearish_score:
        action = "WAIT"
        message = "Bullish and bearish confluence are balanced."
    elif bullish_score > bearish_score:
        action = "WAIT"
        message = "Bullish structure exists, but not enough confirmation for a trade."
    else:
        action = "WAIT"
        message = "Bearish structure exists, but not enough confirmation for a trade."

    return SignalPackage(
        signal=SignalSummary(
            action=action,
            confidence=min(60, max(bullish_score, bearish_score) * 8),
            reasons=(bullish_reasons if bullish_score >= bearish_score else bearish_reasons)[:8],
            warnings=[message],
        ),
        drawings=[],
    )


def _build_trade_signal(
    *,
    symbol: str,
    timeframe: str,
    candles: list[ChartCandle],
    structure: StructureSnapshot,
    created_at: datetime,
    bullish: bool,
    entry_zone: object,
    opposing_zone: object | None,
    score: int,
    reasons: list[str],
    warnings: list[str],
) -> SignalPackage:
    current_price = structure.current_price or candles[-1].close
    atr_value = structure.atr or atr([c.model_dump() for c in candles], 14) or (current_price * 0.001)
    entry_low, entry_high = _zone_bounds(entry_zone)
    if entry_low is None or entry_high is None:
        return SignalPackage(
            signal=SignalSummary(action="WAIT", confidence=0, warnings=["Could not determine an entry zone."]),
            drawings=[],
        )

    entry_mid = (entry_low + entry_high) / 2.0
    if bullish:
        stop_loss = min(entry_low, min((s.price for s in structure.swing_lows[-2:]), default=entry_low)) - atr_value * 0.15
    else:
        stop_loss = max(entry_high, max((s.price for s in structure.swing_highs[-2:]), default=entry_high)) + atr_value * 0.15

    risk = abs(entry_mid - stop_loss)
    if risk <= 0:
        return SignalPackage(
            signal=SignalSummary(action="WAIT", confidence=0, warnings=["Could not derive a valid stop-loss."]),
            drawings=[],
        )

    if opposing_zone is not None:
        opp_low, opp_high = _zone_bounds(opposing_zone)
        opp_mid = _midpoint(opposing_zone)
    else:
        opp_low = opp_high = opp_mid = None

    if bullish:
        target_1 = opp_mid if opp_mid and opp_mid > entry_mid else entry_mid + risk * 1.5
        target_2 = opp_high if opp_high and opp_high > entry_mid else entry_mid + risk * 2.5
        target_3 = max(target_2 + risk, entry_mid + risk * 3.5)
        invalidation = f"Close below {stop_loss:.5f}"
    else:
        target_1 = opp_mid if opp_mid and opp_mid < entry_mid else entry_mid - risk * 1.5
        target_2 = opp_low if opp_low and opp_low < entry_mid else entry_mid - risk * 2.5
        target_3 = min(target_2 - risk, entry_mid - risk * 3.5)
        invalidation = f"Close above {stop_loss:.5f}"

    if bullish:
        risk_reward = (target_1 - entry_mid) / risk if risk else None
        action = "BUY"
    else:
        risk_reward = (entry_mid - target_1) / risk if risk else None
        action = "SELL"

    signal_confidence = min(95, 40 + score * 5)
    signal = SignalSummary(
        action=action,
        confidence=signal_confidence,
        entry_min=round(entry_low, 6),
        entry_max=round(entry_high, 6),
        stop_loss=round(stop_loss, 6),
        take_profit_1=round(target_1, 6),
        take_profit_2=round(target_2, 6),
        take_profit_3=round(target_3, 6),
        risk_reward=round(risk_reward, 2) if risk_reward is not None else None,
        invalidation=invalidation,
        reasons=reasons[:8],
        warnings=warnings[:8],
    )

    last_time = candles[-1].time
    previous_time = candles[-2].time if len(candles) > 1 else candles[-1].time
    drawings: list[BaseDrawing] = [
        EntryZoneDrawing(
            id=f"{symbol}:{timeframe}:entry-zone:{int(last_time.timestamp())}",
            symbol=symbol,
            timeframe=timeframe,
            source=DrawingSource.DETERMINISTIC,
            confidence=signal_confidence,
            label="Entry zone",
            enabled=True,
            created_at=created_at,
            time_start=previous_time,
            time_end=last_time,
            price_low=round(entry_low, 6),
            price_high=round(entry_high, 6),
            style={
                "line_color": "#2563eb" if bullish else "#dc2626",
                "fill_color": "#dbeafe" if bullish else "#fee2e2",
                "text_color": "#0f172a",
                "line_width": 1,
                "opacity": 0.22,
            },
            state="active",
            metadata={"direction": action.lower(), "category": "entry_zone"},
        ),
        StopLossDrawing(
            id=f"{symbol}:{timeframe}:stop-loss:{int(last_time.timestamp())}",
            symbol=symbol,
            timeframe=timeframe,
            source=DrawingSource.DETERMINISTIC,
            confidence=signal_confidence,
            label="Stop loss",
            enabled=True,
            created_at=created_at,
            time_start=previous_time,
            time_end=last_time,
            price_start=round(stop_loss, 6),
            price_end=round(stop_loss, 6),
            style={
                "line_color": "#991b1b",
                "fill_color": "#fee2e2",
                "text_color": "#991b1b",
                "line_width": 2,
                "line_style": "dashed",
                "opacity": 0.24,
            },
            metadata={"direction": action.lower(), "category": "stop_loss"},
        ),
        TakeProfitDrawing(
            id=f"{symbol}:{timeframe}:take-profit-1:{int(last_time.timestamp())}",
            symbol=symbol,
            timeframe=timeframe,
            source=DrawingSource.DETERMINISTIC,
            confidence=signal_confidence,
            label="Take profit 1",
            enabled=True,
            created_at=created_at,
            time_start=previous_time,
            time_end=last_time,
            price_start=round(target_1, 6),
            price_end=round(target_1, 6),
            style={
                "line_color": "#15803d",
                "fill_color": "#dcfce7",
                "text_color": "#166534",
                "line_width": 2,
                "line_style": "solid",
                "opacity": 0.22,
            },
            metadata={"direction": action.lower(), "category": "take_profit"},
        ),
        TakeProfitDrawing(
            id=f"{symbol}:{timeframe}:take-profit-2:{int(last_time.timestamp())}",
            symbol=symbol,
            timeframe=timeframe,
            source=DrawingSource.DETERMINISTIC,
            confidence=max(70, signal_confidence - 5),
            label="Take profit 2",
            enabled=True,
            created_at=created_at,
            time_start=previous_time,
            time_end=last_time,
            price_start=round(target_2, 6),
            price_end=round(target_2, 6),
            style={
                "line_color": "#22c55e",
                "fill_color": "#dcfce7",
                "text_color": "#166534",
                "line_width": 1,
                "line_style": "solid",
                "opacity": 0.2,
            },
            metadata={"direction": action.lower(), "category": "take_profit"},
        ),
        TakeProfitDrawing(
            id=f"{symbol}:{timeframe}:take-profit-3:{int(last_time.timestamp())}",
            symbol=symbol,
            timeframe=timeframe,
            source=DrawingSource.DETERMINISTIC,
            confidence=max(65, signal_confidence - 10),
            label="Take profit 3",
            enabled=True,
            created_at=created_at,
            time_start=previous_time,
            time_end=last_time,
            price_start=round(target_3, 6),
            price_end=round(target_3, 6),
            style={
                "line_color": "#4ade80",
                "fill_color": "#dcfce7",
                "text_color": "#166534",
                "line_width": 1,
                "line_style": "solid",
                "opacity": 0.18,
            },
            metadata={"direction": action.lower(), "category": "take_profit"},
        ),
        RiskRewardBoxDrawing(
            id=f"{symbol}:{timeframe}:risk-reward:{int(last_time.timestamp())}",
            symbol=symbol,
            timeframe=timeframe,
            source=DrawingSource.DETERMINISTIC,
            confidence=signal_confidence,
            label="Risk/reward box",
            enabled=True,
            created_at=created_at,
            time_start=previous_time,
            time_end=last_time,
            entry_low=round(entry_low, 6),
            entry_high=round(entry_high, 6),
            stop_loss=round(stop_loss, 6),
            take_profit_1=round(target_1, 6),
            take_profit_2=round(target_2, 6),
            take_profit_3=round(target_3, 6),
            style={
                "line_color": "#0f172a",
                "fill_color": "#e2e8f0",
                "text_color": "#0f172a",
                "line_width": 1,
                "line_style": "dashed",
                "opacity": 0.16,
            },
            metadata={"direction": action.lower(), "category": "risk_reward"},
        ),
        SignalMarkerDrawing(
            id=f"{symbol}:{timeframe}:signal-marker:{int(last_time.timestamp())}",
            symbol=symbol,
            timeframe=timeframe,
            source=DrawingSource.DETERMINISTIC,
            confidence=signal_confidence,
            label=f"{action} signal",
            enabled=True,
            created_at=created_at,
            time_start=last_time,
            time_end=last_time,
            price_start=entry_mid,
            price_end=entry_mid,
            style={
                "line_color": "#2563eb" if bullish else "#dc2626",
                "fill_color": "#dbeafe" if bullish else "#fee2e2",
                "text_color": "#0f172a",
                "line_width": 1,
                "opacity": 0.28,
            },
            metadata={"direction": action.lower(), "category": "signal_marker"},
        ),
        TextLabelDrawing(
            id=f"{symbol}:{timeframe}:invalidation:{int(last_time.timestamp())}",
            symbol=symbol,
            timeframe=timeframe,
            source=DrawingSource.DETERMINISTIC,
            confidence=signal_confidence,
            label=f"Invalidation: {invalidation}",
            enabled=True,
            created_at=created_at,
            time_start=last_time,
            time_end=last_time,
            price_start=stop_loss,
            price_end=stop_loss,
            style={
                "line_color": "#0f172a",
                "fill_color": "#ffffff",
                "text_color": "#334155",
                "line_width": 0,
                "opacity": 0.0,
            },
            metadata={"direction": action.lower(), "category": "invalidation"},
        ),
    ]

    return SignalPackage(signal=signal, drawings=drawings)

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from math import floor, log10
from typing import Iterable

from .market_structure import StructureSnapshot, SwingPoint
from .models import (
    ChartCandle,
    DrawingSource,
    ExpertFinding,
    ExpertReport,
    HorizontalLineDrawing,
)


@dataclass(slots=True)
class LevelCandidate:
    kind: str
    label: str
    price: float
    score: int
    importance: str
    rationale: str
    metadata: dict
    direction: str = "neutral"


def _clamp_score(value: int) -> int:
    return max(0, min(100, int(value)))


def _price_decimals(price: float) -> int:
    if price >= 100:
        return 2
    if price >= 10:
        return 3
    return 5


def _line_style(kind: str, direction: str) -> dict:
    color = "#64748b"
    if direction == "bullish":
        color = "#16a34a"
    elif direction == "bearish":
        color = "#dc2626"
    elif kind in {"pivot", "psychological"}:
        color = "#7c3aed"
    elif kind.startswith("session"):
        color = "#0284c7"
    return {
        "line_color": color,
        "fill_color": "#ffffff",
        "text_color": color,
        "line_width": 1 if kind != "pivot" else 2,
        "line_style": "dashed" if kind != "psychological" else "dotted",
        "opacity": 0.32,
    }


def _level_drawing(
    *,
    symbol: str,
    timeframe: str,
    created_at: datetime,
    level: LevelCandidate,
    first_time: datetime,
    last_time: datetime,
) -> HorizontalLineDrawing:
    decimals = _price_decimals(level.price)
    level_key = str(round(level.price, decimals)).replace(".", "_")
    return HorizontalLineDrawing(
        id=f"{symbol}:{timeframe}:sr-expert:{level.kind}:{level_key}",
        symbol=symbol,
        timeframe=timeframe,
        source=DrawingSource.DETERMINISTIC,
        confidence=level.score,
        label=level.label,
        enabled=True,
        created_at=created_at,
        time_start=first_time,
        time_end=last_time,
        price_start=round(level.price, decimals),
        price_end=round(level.price, decimals),
        style=_line_style(level.kind, level.direction),
        metadata={
            **level.metadata,
            "expert": "support_resistance",
            "kind": level.kind,
            "importance": level.importance,
            "rationale": level.rationale,
        },
    )


def _nearest_direction(current_price: float, price: float) -> str:
    if price < current_price:
        return "bullish"
    if price > current_price:
        return "bearish"
    return "neutral"


def _period_groups(candles: Iterable[ChartCandle], period: str) -> dict[object, list[ChartCandle]]:
    groups: dict[object, list[ChartCandle]] = defaultdict(list)
    for candle in candles:
        if period == "daily":
            key = candle.time.date()
        elif period == "weekly":
            iso = candle.time.isocalendar()
            key = (iso.year, iso.week)
        elif period == "monthly":
            key = (candle.time.year, candle.time.month)
        else:
            key = candle.time.date()
        groups[key].append(candle)
    return groups


def _previous_period_levels(candles: list[ChartCandle], current_price: float) -> list[LevelCandidate]:
    levels: list[LevelCandidate] = []
    for period, score_base in (("daily", 86), ("weekly", 92), ("monthly", 96)):
        groups = _period_groups(candles, period)
        keys = sorted(groups)
        if len(keys) < 2:
            continue
        previous = groups[keys[-2]]
        high = max(item.high for item in previous)
        low = min(item.low for item in previous)
        levels.append(LevelCandidate(
            kind=f"previous_{period}_high",
            label=f"Previous {period} high",
            price=high,
            score=score_base,
            importance="high" if period != "monthly" else "critical",
            rationale=f"Price often reacts around the prior {period} high.",
            direction=_nearest_direction(current_price, high),
            metadata={"period": period, "source": "previous_period"},
        ))
        levels.append(LevelCandidate(
            kind=f"previous_{period}_low",
            label=f"Previous {period} low",
            price=low,
            score=score_base,
            importance="high" if period != "monthly" else "critical",
            rationale=f"Price often reacts around the prior {period} low.",
            direction=_nearest_direction(current_price, low),
            metadata={"period": period, "source": "previous_period"},
        ))
    return levels


def _session_name(hour: int) -> str:
    if 0 <= hour < 7:
        return "asian"
    if 7 <= hour < 12:
        return "london"
    if 12 <= hour < 16:
        return "london_new_york_overlap"
    if 16 <= hour < 21:
        return "new_york"
    return "post_new_york"


def _session_levels(candles: list[ChartCandle], current_price: float) -> list[LevelCandidate]:
    grouped: dict[tuple[date, str], list[ChartCandle]] = defaultdict(list)
    for candle in candles:
        grouped[(candle.time.date(), _session_name(candle.time.hour))].append(candle)
    keys = sorted(grouped)
    if not keys:
        return []
    recent_keys = keys[-8:]
    levels: list[LevelCandidate] = []
    for session_date, session in recent_keys:
        items = grouped[(session_date, session)]
        if len(items) < 2:
            continue
        high = max(item.high for item in items)
        low = min(item.low for item in items)
        label_session = session.replace("_", " ").title()
        levels.append(LevelCandidate(
            kind=f"session_{session}_high",
            label=f"{label_session} high",
            price=high,
            score=74 if "overlap" not in session else 82,
            importance="medium" if "overlap" not in session else "high",
            rationale=f"{label_session} high can act as intraday liquidity or resistance.",
            direction=_nearest_direction(current_price, high),
            metadata={"session": session, "date": session_date.isoformat(), "source": "session"},
        ))
        levels.append(LevelCandidate(
            kind=f"session_{session}_low",
            label=f"{label_session} low",
            price=low,
            score=74 if "overlap" not in session else 82,
            importance="medium" if "overlap" not in session else "high",
            rationale=f"{label_session} low can act as intraday liquidity or support.",
            direction=_nearest_direction(current_price, low),
            metadata={"session": session, "date": session_date.isoformat(), "source": "session"},
        ))
    return levels


def _pivot_levels(candles: list[ChartCandle], current_price: float) -> list[LevelCandidate]:
    groups = _period_groups(candles, "daily")
    keys = sorted(groups)
    if len(keys) < 2:
        return []
    previous = groups[keys[-2]]
    high = max(item.high for item in previous)
    low = min(item.low for item in previous)
    close = previous[-1].close
    pivot = (high + low + close) / 3
    r1 = 2 * pivot - low
    s1 = 2 * pivot - high
    r2 = pivot + (high - low)
    s2 = pivot - (high - low)
    specs = [
        ("pivot", "Daily pivot", pivot, 84, "high"),
        ("pivot_r1", "Daily pivot R1", r1, 78, "medium"),
        ("pivot_s1", "Daily pivot S1", s1, 78, "medium"),
        ("pivot_r2", "Daily pivot R2", r2, 72, "medium"),
        ("pivot_s2", "Daily pivot S2", s2, 72, "medium"),
    ]
    return [
        LevelCandidate(
            kind=kind,
            label=label,
            price=price,
            score=score,
            importance=importance,
            rationale="Classic floor-trader pivot level from the previous daily range.",
            direction=_nearest_direction(current_price, price),
            metadata={"source": "pivot", "previous_day": keys[-2].isoformat() if hasattr(keys[-2], "isoformat") else str(keys[-2])},
        )
        for kind, label, price, score, importance in specs
    ]


def _psychological_step(current_price: float) -> float:
    if current_price <= 0:
        return 1.0
    magnitude = 10 ** floor(log10(current_price))
    if current_price >= 1000:
        return 10.0
    if current_price >= 100:
        return 1.0
    if current_price >= 10:
        return 0.1
    if current_price >= 1:
        return 0.01
    return magnitude / 10


def _psychological_levels(current_price: float) -> list[LevelCandidate]:
    step = _psychological_step(current_price)
    center = round(current_price / step) * step
    prices = [center + step * offset for offset in range(-3, 4)]
    levels: list[LevelCandidate] = []
    for price in prices:
        if price <= 0:
            continue
        distance_steps = abs(price - current_price) / step
        levels.append(LevelCandidate(
            kind="psychological",
            label=f"Psychological level {price:.{_price_decimals(price)}f}",
            price=price,
            score=_clamp_score(72 - int(distance_steps * 4)),
            importance="medium",
            rationale="Round-number psychological level near current price.",
            direction=_nearest_direction(current_price, price),
            metadata={"source": "psychological", "step": step},
        ))
    return levels


def _swing_levels(structure: StructureSnapshot, current_price: float) -> list[LevelCandidate]:
    levels: list[LevelCandidate] = []

    def add(swings: list[SwingPoint], side: str) -> None:
        for swing in swings[-6:]:
            levels.append(LevelCandidate(
                kind=f"swing_{side}",
                label=f"Swing {side}",
                price=swing.price,
                score=_clamp_score(62 + int(swing.strength * 8)),
                importance="medium",
                rationale=f"Confirmed swing {side} from recent market structure.",
                direction=_nearest_direction(current_price, swing.price),
                metadata={
                    "source": "swing",
                    "index": swing.index,
                    "strength": swing.strength,
                    "confirmed_at": swing.confirmed_at.isoformat(),
                },
            ))

    add(structure.swing_highs, "high")
    add(structure.swing_lows, "low")
    return levels


def _dedupe_levels(levels: list[LevelCandidate], tolerance: float) -> list[LevelCandidate]:
    result: list[LevelCandidate] = []
    for level in sorted(levels, key=lambda item: item.score, reverse=True):
        duplicate = next((item for item in result if abs(item.price - level.price) <= tolerance), None)
        if duplicate:
            duplicate.metadata.setdefault("merged_sources", []).append(level.kind)
            duplicate.score = max(duplicate.score, level.score)
            continue
        result.append(level)
    return sorted(result, key=lambda item: item.score, reverse=True)


def run_support_resistance_expert(
    *,
    symbol: str,
    timeframe: str,
    candles: list[ChartCandle],
    structure: StructureSnapshot,
    created_at: datetime,
    max_drawings: int = 28,
) -> tuple[ExpertReport, list[HorizontalLineDrawing]]:
    current_price = structure.current_price or candles[-1].close
    atr_value = structure.atr or max((item.high - item.low for item in candles[-20:]), default=current_price * 0.001)
    tolerance = max(atr_value * 0.18, current_price * 0.0002)
    levels: list[LevelCandidate] = []
    levels.extend(_previous_period_levels(candles, current_price))
    levels.extend(_session_levels(candles, current_price))
    levels.extend(_pivot_levels(candles, current_price))
    levels.extend(_psychological_levels(current_price))
    levels.extend(_swing_levels(structure, current_price))
    levels = _dedupe_levels(levels, tolerance)
    selected = levels[:max_drawings]
    first_time = candles[0].time
    last_time = candles[-1].time
    drawings = [
        _level_drawing(
            symbol=symbol,
            timeframe=timeframe,
            created_at=created_at,
            level=level,
            first_time=first_time,
            last_time=last_time,
        )
        for level in selected
    ]
    nearby = sorted(selected, key=lambda item: abs(item.price - current_price))[:5]
    above = [item for item in selected if item.price > current_price]
    below = [item for item in selected if item.price < current_price]
    nearest_resistance = min(above, key=lambda item: item.price - current_price, default=None)
    nearest_support = max(below, key=lambda item: item.price, default=None)
    findings = [
        ExpertFinding(
            kind=level.kind,
            label=level.label,
            direction=level.direction,  # type: ignore[arg-type]
            price=round(level.price, _price_decimals(level.price)),
            score=level.score,
            importance=level.importance,  # type: ignore[arg-type]
            rationale=level.rationale,
            metadata=level.metadata,
        )
        for level in nearby
    ]
    summary_parts = []
    if nearest_support:
        summary_parts.append(f"nearest support {nearest_support.price:.{_price_decimals(nearest_support.price)}f}")
    if nearest_resistance:
        summary_parts.append(f"nearest resistance {nearest_resistance.price:.{_price_decimals(nearest_resistance.price)}f}")
    summary = "Support/resistance map built from " + ", ".join(
        ["previous period levels", "session highs/lows", "swings", "psychological levels", "daily pivots"]
    )
    if summary_parts:
        summary += "; " + " and ".join(summary_parts) + "."
    else:
        summary += "."
    score = _clamp_score(round(sum(item.score for item in selected[:10]) / max(1, min(10, len(selected)))))
    report = ExpertReport(
        id="support_resistance",
        name="Support & Resistance Expert",
        category="levels",
        score=score,
        bias="neutral",
        confidence=score,
        summary=summary,
        findings=findings,
        warnings=[] if len(candles) >= 80 else ["Limited candle history reduces higher-timeframe level quality."],
        drawing_ids=[drawing.id for drawing in drawings],
        metadata={
            "level_count": len(selected),
            "nearest_support": nearest_support.price if nearest_support else None,
            "nearest_resistance": nearest_resistance.price if nearest_resistance else None,
            "tolerance": tolerance,
        },
    )
    return report, drawings

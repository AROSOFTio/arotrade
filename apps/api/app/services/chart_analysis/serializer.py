from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Iterable, Sequence

from .models import ChartAnalysisResponse, ChartDrawing


def drawing_category(drawing_type: str) -> str:
    mapping = {
        "horizontal_line": "structure",
        "trend_line": "trendlines",
        "ray": "trendlines",
        "rectangle": "zones",
        "support_zone": "support_resistance",
        "resistance_zone": "support_resistance",
        "supply_zone": "supply_demand",
        "demand_zone": "supply_demand",
        "order_block": "supply_demand",
        "breaker_block": "supply_demand",
        "fair_value_gap": "fvg",
        "liquidity_zone": "liquidity",
        "swing_high": "structure",
        "swing_low": "structure",
        "fibonacci": "fibonacci",
        "entry_zone": "trade_levels",
        "stop_loss": "trade_levels",
        "take_profit": "trade_levels",
        "risk_reward_box": "trade_levels",
        "text_label": "labels",
        "signal_marker": "labels",
    }
    return mapping.get(drawing_type, "misc")


def filter_drawings(drawings: Sequence[ChartDrawing], include: set[str] | None) -> list[ChartDrawing]:
    if not include or "all" in include:
        return list(drawings)

    allowed_categories = {token.strip().lower() for token in include if token.strip()}
    filtered: list[ChartDrawing] = []
    for drawing in drawings:
        category = drawing_category(drawing.type)
        if category in allowed_categories or drawing.type in allowed_categories:
            filtered.append(drawing)
    return filtered


def analysis_cache_key(
    *,
    account_id: int,
    broker_symbol: str,
    timeframe: str,
    latest_candle_time: datetime,
    count: int,
    include: set[str] | None,
    analysis_version: str,
) -> str:
    include_key = ",".join(sorted(token.strip().lower() for token in (include or set()) if token.strip())) or "all"
    candle_key = latest_candle_time.isoformat()
    raw = f"{account_id}|{broker_symbol.upper()}|{timeframe.upper()}|{count}|{candle_key}|{include_key}|{analysis_version}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"arotrade:chart-analysis:{digest}"


def serialize_analysis(analysis: ChartAnalysisResponse) -> dict:
    return analysis.model_dump(mode="json")


def serialize_analysis_json(analysis: ChartAnalysisResponse) -> str:
    return json.dumps(serialize_analysis(analysis), separators=(",", ":"), ensure_ascii=False)


def deserialize_analysis_json(payload: str) -> ChartAnalysisResponse:
    return ChartAnalysisResponse.model_validate_json(payload)

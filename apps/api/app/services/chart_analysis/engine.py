from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from datetime import UTC, datetime
from threading import Lock
from typing import Optional

from app.config import settings
from app.services.gemini import AIProviderError, AIProviderNotConfigured, analyze_json

from .fibonacci import detect_fibonacci
from .market_structure import (
    StructureSnapshot,
    build_structure_drawings,
    detect_market_structure,
    normalize_candles,
    parse_chart_time,
    timeframe_to_seconds,
)
from .models import (
    ChartAnalysisResponse,
    ChartCandle,
    ExplanationSummary,
    IndicatorSummary,
    MarketState,
    SignalSummary,
)
from .patterns import detect_chart_patterns
from .serializer import analysis_cache_key, deserialize_analysis_json, filter_drawings, serialize_analysis_json
from .signals import SignalPackage, derive_signal
from .trendlines import detect_trendlines
from .zones import (
    detect_fair_value_gaps,
    detect_liquidity_zones,
    detect_order_blocks,
    detect_supply_demand_zones,
    detect_support_resistance_zones,
)


logger = logging.getLogger(__name__)

ANALYSIS_VERSION = "1.0"
CACHE_TTL_SECONDS = 15 * 60
_memory_cache: dict[str, tuple[float, str]] = {}
_memory_lock = Lock()

try:
    import redis
except Exception:  # pragma: no cover - optional at import time
    redis = None


def _redis_client():
    if redis is None:
        return None
    try:
        return redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
    except Exception:
        return None


def parse_include(value: Optional[str]) -> set[str]:
    if not value:
        return {"all"}
    tokens = {token.strip().lower() for token in value.split(",") if token.strip()}
    return tokens or {"all"}


def _cache_get(cache_key: str) -> Optional[ChartAnalysisResponse]:
    client = _redis_client()
    if client:
        try:
            raw = client.get(cache_key)
            if raw:
                return deserialize_analysis_json(raw.decode("utf-8"))
        except Exception:
            pass
    now = time.monotonic()
    with _memory_lock:
        entry = _memory_cache.get(cache_key)
        if entry and entry[0] > now:
            try:
                return deserialize_analysis_json(entry[1])
            except Exception:
                return None
    return None


def _cache_set(cache_key: str, analysis: ChartAnalysisResponse) -> None:
    payload = serialize_analysis_json(analysis)
    client = _redis_client()
    if client:
        try:
            client.setex(cache_key, CACHE_TTL_SECONDS, payload)
        except Exception:
            pass
    with _memory_lock:
        _memory_cache[cache_key] = (time.monotonic() + CACHE_TTL_SECONDS, payload)


def cache_analysis(
    *,
    account_id: int,
    broker_symbol: str,
    timeframe: str,
    latest_candle_time: datetime,
    count: int,
    include: set[str] | None,
    analysis: ChartAnalysisResponse,
) -> str:
    key = analysis_cache_key(
        account_id=account_id,
        broker_symbol=broker_symbol,
        timeframe=timeframe,
        latest_candle_time=latest_candle_time,
        count=count,
        include=include,
        analysis_version=ANALYSIS_VERSION,
    )
    _cache_set(key, analysis)
    return key


def get_cached_analysis(
    *,
    account_id: int,
    broker_symbol: str,
    timeframe: str,
    latest_candle_time: datetime,
    count: int,
    include: set[str] | None,
) -> Optional[ChartAnalysisResponse]:
    key = analysis_cache_key(
        account_id=account_id,
        broker_symbol=broker_symbol,
        timeframe=timeframe,
        latest_candle_time=latest_candle_time,
        count=count,
        include=include,
        analysis_version=ANALYSIS_VERSION,
    )
    return _cache_get(key)


def publish_analysis_event(account_id: int, payload: dict) -> None:
    client = _redis_client()
    if not client:
        return
    try:
        client.publish(f"channel:analysis:{account_id}", json.dumps(payload, default=str))
    except Exception:
        return


def _safe_call(warnings: list[str], label: str, func):
    try:
        return func()
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.exception("%s detector failed: %s", label, exc)
        warnings.append(f"{label} detector failed: {exc}")
        return None


def _build_deterministic_explanation(
    *,
    symbol: str,
    timeframe: str,
    structure: StructureSnapshot,
    signal: SignalSummary,
    warnings: list[str],
) -> ExplanationSummary:
    summary = (
        f"{symbol} on {timeframe} is {structure.bias} with {structure.trend} price action "
        f"and {structure.structure} swing structure."
    )
    observations = [
        f"Current price is {structure.current_price:.5f}" if structure.current_price else "Current price is unavailable.",
    ]
    if structure.ema20 is not None and structure.ema50 is not None:
        observations.append(f"EMA20 is {'above' if structure.ema20 > structure.ema50 else 'below'} EMA50.")
    if structure.ema200 is not None and structure.ema50 is not None:
        observations.append(f"EMA50 is {'above' if structure.ema50 > structure.ema200 else 'below'} EMA200.")
    if structure.rsi14 is not None:
        observations.append(f"RSI14 sits at {structure.rsi14:.1f}.")
    if structure.events:
        observations.extend(event.description for event in structure.events[:3])
    if signal.reasons:
        observations.extend(signal.reasons[:3])

    plan = {
        "BUY": "Look for bullish confirmation near the identified entry zone and only proceed if the market respects invalidation.",
        "SELL": "Look for bearish confirmation near the identified entry zone and only proceed if the market respects invalidation.",
        "WAIT": "No trade is justified yet. Continue monitoring for a stronger setup.",
        "AVOID": "Conditions are too weak or stale for a responsible setup.",
    }.get(signal.action, "No actionable plan.")

    risk_note = signal.invalidation or "Keep risk tied to the invalidation level and the existing risk engine."
    if warnings:
        risk_note = f"{risk_note} Warnings: {'; '.join(warnings[:3])}."
    return ExplanationSummary(summary=summary, observations=observations[:8], plan=plan, risk_note=risk_note)


def _maybe_generate_ai_explanation(
    *,
    symbol: str,
    timeframe: str,
    structure: StructureSnapshot,
    signal: SignalSummary,
    explanation: ExplanationSummary,
    warnings: list[str],
) -> tuple[ExplanationSummary, list[str]]:
    if not settings.AI_PROVIDER_ORDER:
        warnings.append("AI explanation skipped because no provider is configured.")
        return explanation, warnings

    prompt = (
        "You are explaining a deterministic chart-analysis result. Return only JSON with "
        "keys summary, observations, plan, risk_note. Do not invent prices or levels, "
        "do not change numeric facts, and keep the language simple.\n\n"
        f"Symbol: {symbol}\n"
        f"Timeframe: {timeframe}\n"
        f"Market state: {json.dumps(asdict(structure), default=str)}\n"
        f"Signal: {signal.model_dump(mode='json')}\n"
        f"Deterministic explanation: {explanation.model_dump(mode='json')}\n"
    )

    try:
        data = analyze_json(prompt, temperature=0.2)
    except AIProviderNotConfigured:
        warnings.append("AI explanation skipped because no provider is configured.")
        return explanation, warnings
    except AIProviderError as exc:
        warnings.append(f"AI explanation unavailable: {exc}")
        return explanation, warnings

    try:
        ai_explanation = ExplanationSummary.model_validate(data)
    except Exception as exc:
        warnings.append(f"AI explanation returned an invalid schema: {exc}")
        return explanation, warnings

    return ai_explanation, warnings


def analyze_chart(
    *,
    symbol: str,
    broker_symbol: str,
    timeframe: str,
    candles: list[dict],
    include: Optional[str] = None,
    generated_at: Optional[datetime] = None,
) -> ChartAnalysisResponse:
    started = time.perf_counter()
    include_set = parse_include(include)
    normalized = normalize_candles(candles)
    warnings: list[str] = []
    now = generated_at or datetime.now(UTC)

    if not normalized:
        raise ValueError("No valid candles were provided for analysis")

    if len(normalized) < 50:
        warnings.append("Fewer than 50 candles were available, so some detectors may be incomplete.")
    if len(normalized) < 200:
        warnings.append("EMA200 and some pattern detectors may be unavailable because the candle history is short.")

    last_candle = normalized[-1]
    interval_seconds = timeframe_to_seconds(timeframe)
    candle_age = (now - last_candle.time).total_seconds()
    if candle_age > interval_seconds * 3:
        warnings.append(
            f"Latest candle is {candle_age:.0f}s old, which is older than expected for {timeframe} data."
        )

    structure = _safe_call(warnings, "market structure", lambda: detect_market_structure(normalized, timeframe))
    if structure is None:
        raise ValueError("Market structure analysis failed")

    indicator_summary = IndicatorSummary(
        ema20=structure.ema20,
        ema50=structure.ema50,
        ema200=structure.ema200,
        rsi14=structure.rsi14,
        macd=structure.macd,
        macd_signal=structure.macd_signal,
        macd_histogram=structure.macd_histogram,
        atr14=structure.atr,
    )
    market_state = MarketState(
        bias=structure.bias,
        trend=structure.trend,
        volatility=structure.volatility,
        structure=structure.structure,
        current_price=structure.current_price,
        atr=structure.atr,
    )

    base_drawings: list[object] = build_structure_drawings(
        symbol=symbol,
        timeframe=timeframe,
        candles=normalized,
        structure=structure,
        created_at=now,
    )
    optional_drawings: list[object] = []
    signal_context_drawings: list[object] = list(base_drawings)

    detector_groups = [
        ("support_resistance", lambda: detect_support_resistance_zones(symbol=symbol, timeframe=timeframe, candles=normalized, structure=structure, created_at=now)),
        ("supply_demand", lambda: detect_supply_demand_zones(symbol=symbol, timeframe=timeframe, candles=normalized, structure=structure, created_at=now)),
        ("order_blocks", lambda: detect_order_blocks(symbol=symbol, timeframe=timeframe, candles=normalized, structure=structure, created_at=now)),
        ("fvg", lambda: detect_fair_value_gaps(symbol=symbol, timeframe=timeframe, candles=normalized, created_at=now)),
        ("liquidity", lambda: detect_liquidity_zones(symbol=symbol, timeframe=timeframe, candles=normalized, structure=structure, created_at=now)),
        ("trendlines", lambda: detect_trendlines(symbol=symbol, timeframe=timeframe, candles=normalized, structure=structure, created_at=now)),
        ("fibonacci", lambda: detect_fibonacci(symbol=symbol, timeframe=timeframe, candles=normalized, structure=structure, created_at=now)),
        ("patterns", lambda: detect_chart_patterns(symbol=symbol, timeframe=timeframe, candles=normalized, structure=structure, created_at=now)),
    ]

    for label, detector in detector_groups:
        if include_set != {"all"} and label not in include_set and "all" not in include_set:
            # Keep the core structure drawings and trade levels, but allow callers
            # to narrow the optional overlay set.
            continue
        result = _safe_call(warnings, label, detector)
        if result:
            optional_drawings.extend(result)
            signal_context_drawings.extend(result)

    signal_package = _safe_call(
        warnings,
        "signal",
        lambda: derive_signal(
            symbol=symbol,
            timeframe=timeframe,
            candles=normalized,
            structure=structure,
            drawings=signal_context_drawings,
            created_at=now,
        ),
    )
    if not isinstance(signal_package, SignalPackage):
        signal_package = SignalPackage(signal=SignalSummary(action="WAIT", confidence=0, warnings=["Signal generation failed."]), drawings=[])
        warnings.append("Signal generation failed.")

    drawings = list(base_drawings)
    drawings.extend(filter_drawings(optional_drawings, include_set))
    drawings.extend(signal_package.drawings)

    explanation = _build_deterministic_explanation(
        symbol=symbol,
        timeframe=timeframe,
        structure=structure,
        signal=signal_package.signal,
        warnings=warnings,
    )
    if "ai" in include_set:
        explanation, warnings = _maybe_generate_ai_explanation(
            symbol=symbol,
            timeframe=timeframe,
            structure=structure,
            signal=signal_package.signal,
            explanation=explanation,
            warnings=warnings,
        )

    response = ChartAnalysisResponse(
        symbol=symbol.upper(),
        broker_symbol=broker_symbol,
        timeframe=timeframe.upper(),
        generated_at=now,
        last_candle_time=last_candle.time,
        analysis_version=ANALYSIS_VERSION,
        market_state=market_state,
        indicators=indicator_summary,
        drawings=drawings,
        signal=signal_package.signal,
        explanation=explanation,
        warnings=warnings,
    )

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    logger.info(
        "chart analysis completed for %s %s %s in %.1fms (%d drawings, %d warnings)",
        symbol,
        broker_symbol,
        timeframe,
        elapsed_ms,
        len(drawings),
        len(warnings),
    )
    return response

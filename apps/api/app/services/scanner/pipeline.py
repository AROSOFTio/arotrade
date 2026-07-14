"""Full automatic signal discovery pipeline.

This is the main orchestration layer that runs on each new closed candle:

1. Subscribe to broker quotes and candles (via MetaApi gateway)
2. On new candle close:
   a. Pre-screen with deterministic TA (cheap, no AI)
   b. If candidate found -> call Gemini for validation/explanation
   c. Post-validate Gemini's response
   d. Create Signal record with fingerprint (idempotent)
   e. Create Notification
3. Monitor approved signals for entry-zone price hits
4. Never call Gemini on every tick - only on qualifying candidates

The pipeline is designed to run inside a Celery task or an asyncio loop
so it does not block the API process.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, UTC, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.services.scanner.indicators import (
    ema, rsi, macd, atr, trend_structure, spread_in_points
)
from app.services.scanner.strategies import run_all_strategies, CandidateSignal
from app.services.scanner.validator import (
    pre_screen_candidate,
    validate_signal_candidate,
    build_signal_fingerprint,
)
from app.services.notify import notify_signal_event, create_notification

logger = logging.getLogger(__name__)


def _call_ai_validation(
    candidate: CandidateSignal,
    candles: list[dict],
    symbol: str,
    timeframe: str,
    bid: float,
    ask: float,
) -> Optional[dict]:
    """
    Call AI to validate a TA-discovered candidate.

    Returns the parsed Gemini response dict or None if AI is unavailable.
    Never lets Gemini override the numeric levels from the strategy engine.
    AI can:
      - Return buy/sell/hold (hold = reject)
      - Adjust confidence within +/-15 points
      - Explain the setup in simple language
      - Identify conflicting evidence
      - Identify news risks
    """
    try:
        from app.services.gemini import ai_health_details, run_chart_analysis, GeminiError, GeminiNotConfigured
        from app.services.metaapi_gateway import candles_to_prompt_context
    except ImportError:
        return None

    if not ai_health_details()["is_available"]:
        return None

    price_context = candles_to_prompt_context(candles, max_rows=120)

    scanner_prompt = (
        f"A technical strategy ({candidate.strategy_name}) has identified the following "
        f"setup on {symbol} {timeframe}:\n\n"
        f"Direction: {candidate.direction.upper()}\n"
        f"Entry zone: {candidate.entry_min} - {candidate.entry_max}\n"
        f"Stop-loss: {candidate.stop_loss}\n"
        f"Take-profit 1: {candidate.take_profit_1}\n"
        f"Risk/reward: {candidate.risk_reward:.2f}\n"
        f"Strategy reasoning: {'; '.join(candidate.reasoning)}\n"
        f"Invalidation: {candidate.invalidation_condition}\n\n"
        f"Current bid: {bid} | ask: {ask}\n\n"
        "Your job:\n"
        "1. Review the candle data below and the proposed levels.\n"
        "2. Identify any conflicting evidence (diverging higher timeframe structure, "
        "   important news in the next 8h, excessive volatility, etc.).\n"
        "3. Return your analysis using the standard JSON schema.\n"
        "4. Use the EXACT SAME entry_min, entry_max, stop_loss, and take_profit_1 "
        "   from the strategy unless there is a clear structural error.\n"
        "5. Adjust confidence based on your analysis (strategy assigned "
        f"   {candidate.confidence}% - your final score should reflect your conviction).\n"
        "6. Signal 'hold' only if there is a genuine structural conflict.\n"
        "7. Never claim guaranteed results."
    )

    try:
        result = run_chart_analysis(
            symbol=symbol,
            timeframe=timeframe,
            prompt=scanner_prompt,
            price_context=price_context,
        )
        return result
    except (GeminiNotConfigured, GeminiError) as exc:
        logger.warning("AI validation failed for %s %s: %s", symbol, timeframe, exc)
        return None
    except Exception as exc:
        logger.error("Unexpected AI provider error: %s", exc, exc_info=True)
        return None


def _candle_age_seconds(candles: list[dict]) -> float:
    """Seconds since the last candle closed."""
    if not candles:
        return float("inf")
    last = candles[-1]
    t = last.get("time") or last.get("brokerTime")
    if not t:
        return float("inf")
    try:
        if isinstance(t, (int, float)):
            candle_time = datetime.fromtimestamp(t, UTC)
        else:
            candle_time = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
        return (datetime.now(UTC) - candle_time).total_seconds()
    except Exception:
        return float("inf")


def run_scanner_pipeline(
    *,
    db: Session,
    scanner_profile: models.ScannerProfile,
    candles: list[dict],
    symbol: str,               # canonical symbol (XAUUSD)
    broker_symbol: str,        # broker symbol (XAUUSDm)
    timeframe: str,
    bid: float,
    ask: float,
    spread_points: Optional[float],
    user: models.User,
    now: Optional[datetime] = None,
) -> Optional[models.Signal]:
    """
    Run the full scan pipeline for one symbol/timeframe on one closed candle.

    Returns the created Signal or None if no qualifying setup was found.
    """
    now = now or datetime.now(UTC).replace(tzinfo=None)

    # -----------------------------------------------------------------------
    # Step 1: Basic candle freshness check
    # -----------------------------------------------------------------------
    candle_age = _candle_age_seconds(candles)
    max_candle_age = 300.0  # 5 minutes max

    # -----------------------------------------------------------------------
    # Step 2: Run strategy engine (deterministic TA)
    # -----------------------------------------------------------------------
    enabled_strategy_ids = scanner_profile.active_strategy_ids or None
    candidate = run_all_strategies(candles, bid, ask, enabled_strategy_ids)

    if candidate is None:
        logger.debug("No candidate found for %s %s", symbol, timeframe)
        return None

    logger.info(
        "Candidate found: %s %s %s (confidence=%d, RR=%.2f)",
        candidate.direction, symbol, timeframe,
        candidate.confidence, candidate.risk_reward,
    )

    # -----------------------------------------------------------------------
    # Step 3: Pre-screen (fast check before Gemini)
    # -----------------------------------------------------------------------
    closes = [c["close"] for c in candles]
    rsi_val = rsi(closes, 14)
    macd_val = macd(closes)

    pre = pre_screen_candidate(
        trend=trend_structure(closes),
        rsi_value=rsi_val,
        macd_histogram=macd_val["histogram"] if macd_val else None,
        atr_value=atr(candles, 14),
        spread_points=spread_points,
        max_spread_points=scanner_profile.max_spread_points,
    )

    if not pre.passed:
        logger.debug("Pre-screen failed for %s %s: %s", symbol, timeframe, pre.reasons)
        return None

    # -----------------------------------------------------------------------
    # Step 4: Build fingerprint and check for duplicates
    # -----------------------------------------------------------------------
    candle_close_time = None
    if candles:
        last_t = candles[-1].get("time") or candles[-1].get("brokerTime")
        if isinstance(last_t, (int, float)):
            candle_close_time = datetime.fromtimestamp(last_t, UTC).replace(tzinfo=None)
        elif last_t:
            try:
                candle_close_time = datetime.fromisoformat(str(last_t).replace("Z", "")).replace(tzinfo=None)
            except Exception:
                pass

    fingerprint = build_signal_fingerprint(
        scanner_profile_id=scanner_profile.id,
        broker_account_id=scanner_profile.broker_account_id,
        broker_symbol=broker_symbol,
        timeframe=timeframe,
        strategy_id=None,   # Using string strategy_id from candidate
        candle_close_time=candle_close_time,
        direction=candidate.direction,
    )

    existing = db.query(models.Signal).filter(
        models.Signal.fingerprint == fingerprint
    ).first()

    if existing:
        logger.info(
            "Duplicate signal fingerprint %s - skipping (existing id=%d)", fingerprint, existing.id
        )
        return None

    # -----------------------------------------------------------------------
    # Step 5: AI validation
    # -----------------------------------------------------------------------
    gemini_result = _call_ai_validation(
        candidate, candles, symbol, timeframe, bid, ask
    )

    # -----------------------------------------------------------------------
    # Step 6: Merge AI result into candidate
    # -----------------------------------------------------------------------
    confidence = candidate.confidence
    reasoning = list(candidate.reasoning)
    news_warning = None
    invalidation = candidate.invalidation_condition
    final_direction = candidate.direction

    if gemini_result:
        gemini_signal = gemini_result.get("signal", "hold")
        if gemini_signal == "hold":
            logger.info(
                "AI validation returned hold for %s %s - signal rejected", symbol, timeframe
            )
            return None

        # Gemini must agree on direction
        if gemini_signal != candidate.direction:
            logger.info(
                "AI validation disagrees with strategy direction (%s vs %s) for %s %s",
                gemini_signal, candidate.direction, symbol, timeframe,
            )
            return None

        # Adjust confidence (strategy confidence +/- Gemini delta, capped to max +/-15)
        gemini_conf = gemini_result.get("confidence", confidence)
        delta = max(-15, min(15, gemini_conf - candidate.confidence))
        confidence = max(0, min(100, candidate.confidence + delta))

        if gemini_result.get("reasoning"):
            reasoning.extend(gemini_result["reasoning"])
        if gemini_result.get("news_warning"):
            news_warning = gemini_result["news_warning"]
        if gemini_result.get("invalidation"):
            invalidation = gemini_result["invalidation"]

    # -----------------------------------------------------------------------
    # Step 7: Post-validate merged candidate
    # -----------------------------------------------------------------------
    current_price = (bid + ask) / 2.0
    post = validate_signal_candidate(
        direction=candidate.direction,
        entry_min=candidate.entry_min,
        entry_max=candidate.entry_max,
        stop_loss=candidate.stop_loss,
        take_profit_1=candidate.take_profit_1,
        confidence=confidence,
        risk_reward=candidate.risk_reward,
        current_price=current_price,
        spread_points=spread_points,
        max_spread_points=scanner_profile.max_spread_points,
        signal_rr_minimum=scanner_profile.minimum_risk_reward,
        confidence_minimum=int(scanner_profile.minimum_confidence),
        candle_age_seconds=candle_age,
        max_candle_age_seconds=max_candle_age,
        existing_fingerprint=False,  # Already checked above
    )

    if not post.passed:
        logger.info(
            "Post-validation failed for %s %s: %s", symbol, timeframe, post.reasons
        )
        return None

    # -----------------------------------------------------------------------
    # Step 8: Create Signal record
    # -----------------------------------------------------------------------
    valid_until = now + timedelta(minutes=scanner_profile.maximum_signal_age_minutes)

    if not scanner_profile.approval_required:
        initial_status = models.SignalStatus.APPROVED
        initial_lifecycle = models.SignalLifecycleStatus.APPROVED_WAITING_ENTRY.value
        approved_at = now
    else:
        initial_status = models.SignalStatus.PENDING
        initial_lifecycle = models.SignalLifecycleStatus.PENDING_APPROVAL.value
        approved_at = None

    signal = models.Signal(
        user_id=user.id,
        source="auto",
        scanner_profile_id=scanner_profile.id,
        broker_account_id=scanner_profile.broker_account_id,
        symbol=symbol,
        canonical_symbol=symbol,
        broker_symbol=broker_symbol,
        timeframe=timeframe,
        signal_type=candidate.direction,
        source_candle_time=candle_close_time,
        detected_price=current_price,
        latest_price=current_price,
        entry_min=candidate.entry_min,
        entry_max=candidate.entry_max,
        stop_loss=candidate.stop_loss,
        take_profit_1=candidate.take_profit_1,
        take_profit_2=candidate.take_profit_2,
        take_profit_3=candidate.take_profit_3,
        risk_reward=candidate.risk_reward,
        confidence=confidence,
        status=initial_status,
        lifecycle_status=initial_lifecycle,
        reasoning=reasoning,
        invalidation=invalidation,
        news_warning=news_warning,
        fingerprint=fingerprint,
        valid_until=valid_until,
        approved_at=approved_at,
    )

    try:
        db.add(signal)
        db.flush()  # Get the ID

        # Create notification
        create_notification(
            db,
            user_id=user.id,
            title=f"Auto signal: {candidate.direction.upper()} {symbol}",
            body=(
                f"{symbol} {timeframe} | {candidate.direction.upper()} | "
                f"Entry {candidate.entry_min:.5f}-{candidate.entry_max:.5f} | "
                f"SL {candidate.stop_loss:.5f} | TP {candidate.take_profit_1:.5f} | "
                f"Confidence {confidence}% | RR {candidate.risk_reward:.1f}"
            ),
            category="signal",
            link=f"/dashboard/signals?signal={signal.id}",
        )

        db.commit()
        db.refresh(signal)

        logger.info(
            "Auto signal created: id=%d %s %s %s (confidence=%d, fingerprint=%s...)",
            signal.id, candidate.direction, symbol, timeframe, confidence, fingerprint[:8],
        )
        return signal

    except Exception as exc:
        db.rollback()
        logger.error(
            "Failed to persist signal for %s %s: %s", symbol, timeframe, exc
        )
        # If this is a unique-constraint violation (race condition), it's safe to ignore
        if "uq_signal_fingerprint" in str(exc).lower() or "unique" in str(exc).lower():
            logger.info("Signal fingerprint race condition - already exists")
        return None


def check_entry_zone(
    signal: models.Signal,
    bid: float,
    ask: float,
) -> bool:
    """
    Check whether the current broker price is inside the signal entry zone.

    For BUY: use ask price (execution price)
    For SELL: use bid price (execution price)
    """
    if not signal.entry_min or not signal.entry_max:
        return False

    if signal.signal_type == "buy":
        return signal.entry_min <= ask <= signal.entry_max
    elif signal.signal_type == "sell":
        return signal.entry_min <= bid <= signal.entry_max
    return False

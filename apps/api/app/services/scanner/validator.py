"""Deterministic signal validation.

This validator runs TWICE:
  1. BEFORE Gemini — to pre-screen candidates (fast, cheap)
  2. AFTER Gemini  — to validate the AI's proposed levels

Gemini must NEVER be the sole authority for numeric levels.
These rules are hard gates; a signal that fails any of them is rejected.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)

    def fail(self, reason: str) -> None:
        self.passed = False
        self.reasons.append(reason)

    def to_dict(self) -> dict:
        return {"passed": self.passed, "reasons": self.reasons}


def validate_signal_candidate(
    *,
    direction: str,
    entry_min: Optional[float],
    entry_max: Optional[float],
    stop_loss: Optional[float],
    take_profit_1: Optional[float],
    confidence: int,
    risk_reward: Optional[float],
    current_price: float,
    spread_points: Optional[float],
    max_spread_points: Optional[float],
    signal_rr_minimum: float,
    confidence_minimum: int,
    candle_age_seconds: float,
    max_candle_age_seconds: float = 300.0,
    existing_fingerprint: bool = False,
    profile_max_entry_distance_pct: float = 0.01,
) -> ValidationResult:
    """
    Full deterministic validation of a signal candidate.

    This is the gate that runs after Gemini returns its analysis.
    It must reject anything that could lead to a bad order.
    """
    r = ValidationResult(passed=True)

    # -----------------------------------------------------------------------
    # Basic structure
    # -----------------------------------------------------------------------
    if direction not in ("buy", "sell"):
        r.fail("Signal direction must be 'buy' or 'sell' (not 'hold')")

    if entry_min is None or entry_max is None:
        r.fail("Entry zone (entry_min and entry_max) is required")
    elif entry_min <= 0 or entry_max <= 0:
        r.fail("Entry prices must be positive")
    elif entry_min > entry_max:
        r.fail("entry_min must be less than or equal to entry_max")

    if stop_loss is None or stop_loss <= 0:
        r.fail("Stop-loss is required")

    if take_profit_1 is None or take_profit_1 <= 0:
        r.fail("At least one take-profit target is required")

    if not r.passed or entry_min is None or stop_loss is None or take_profit_1 is None:
        return r

    # -----------------------------------------------------------------------
    # Direction-specific level validation
    # -----------------------------------------------------------------------
    if direction == "buy":
        if stop_loss >= entry_min:
            r.fail(f"Buy stop-loss ({stop_loss}) must be below entry_min ({entry_min})")
        if take_profit_1 <= entry_max:
            r.fail(f"Buy take-profit ({take_profit_1}) must be above entry_max ({entry_max})")

    elif direction == "sell":
        if stop_loss <= entry_max:
            r.fail(f"Sell stop-loss ({stop_loss}) must be above entry_max ({entry_max})")
        if take_profit_1 >= entry_min:
            r.fail(f"Sell take-profit ({take_profit_1}) must be below entry_min ({entry_min})")

    # -----------------------------------------------------------------------
    # Risk/reward
    # -----------------------------------------------------------------------
    if risk_reward is not None and risk_reward < signal_rr_minimum:
        r.fail(
            f"Risk/reward {risk_reward:.2f} is below the required minimum {signal_rr_minimum:.2f}"
        )

    # -----------------------------------------------------------------------
    # Confidence
    # -----------------------------------------------------------------------
    if confidence < confidence_minimum:
        r.fail(
            f"Confidence {confidence}% is below the required minimum {confidence_minimum}%"
        )

    # -----------------------------------------------------------------------
    # Spread
    # -----------------------------------------------------------------------
    if max_spread_points is not None and spread_points is not None:
        if spread_points > max_spread_points:
            r.fail(
                f"Current spread {spread_points:.1f} points exceeds maximum {max_spread_points:.1f} points"
            )

    # -----------------------------------------------------------------------
    # Candle freshness
    # -----------------------------------------------------------------------
    if candle_age_seconds > max_candle_age_seconds:
        r.fail(
            f"Most recent candle is {candle_age_seconds:.0f}s old "
            f"(limit {max_candle_age_seconds:.0f}s). Data may be stale."
        )

    # -----------------------------------------------------------------------
    # Entry distance from current price (detect setups too far away)
    # -----------------------------------------------------------------------
    if current_price > 0 and entry_min is not None and entry_max is not None:
        mid_entry = (entry_min + entry_max) / 2
        distance_pct = abs(current_price - mid_entry) / current_price
        if distance_pct > profile_max_entry_distance_pct:
            r.fail(
                f"Entry zone is {distance_pct * 100:.2f}% away from current price "
                f"{current_price} — setup may be stale or unrealistic"
            )

    # -----------------------------------------------------------------------
    # Deduplication
    # -----------------------------------------------------------------------
    if existing_fingerprint:
        r.fail(
            "A signal with the same fingerprint already exists. "
            "The same candle cannot generate the same signal twice."
        )

    return r


def pre_screen_candidate(
    *,
    trend: str,
    rsi_value: Optional[float],
    macd_histogram: Optional[float],
    atr_value: Optional[float],
    spread_points: Optional[float],
    max_spread_points: Optional[float],
    min_confidence_for_scan: int = 60,
) -> ValidationResult:
    """
    Cheap pre-screen BEFORE calling Gemini.

    This runs on every candle close and filters out setups that have no
    chance of passing validation. Only candidates that pass here get sent
    to Gemini (controlling API costs).
    """
    r = ValidationResult(passed=True)

    # RSI extreme zones: potential for reversal / continuation
    if rsi_value is not None:
        if 45 <= rsi_value <= 55:
            # Neutral RSI — no strong bias
            r.fail("RSI is in neutral zone (45-55) — no directional conviction")

    # Spread filter (before Gemini call)
    if max_spread_points is not None and spread_points is not None:
        if spread_points > max_spread_points * 1.5:
            r.fail(
                f"Spread {spread_points:.1f}pts is excessively wide. Skipping this candle."
            )

    return r


def build_signal_fingerprint(
    scanner_profile_id: Optional[int],
    broker_account_id: Optional[int],
    broker_symbol: str,
    timeframe: str,
    strategy_id: Optional[int],
    candle_close_time: Optional[datetime],
    direction: str,
) -> str:
    """
    Build a reproducible fingerprint string for deduplication.

    This MUST be idempotent: the same inputs always produce the same
    fingerprint so database-level UNIQUE constraints can catch duplicates.
    """
    import hashlib
    candle_ts = candle_close_time.isoformat() if candle_close_time else "unknown"
    raw = (
        f"{scanner_profile_id}|{broker_account_id}|{broker_symbol.upper()}|"
        f"{timeframe.upper()}|{strategy_id}|{candle_ts}|{direction.lower()}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:64]

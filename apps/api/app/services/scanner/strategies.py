"""Pluggable strategy engine.

Each strategy is a Python class that:
  1. Receives a candle list and indicator results
  2. Returns a CandidateSignal or None

Strategies are registered in STRATEGY_REGISTRY.

The engine calls all enabled strategies and returns the highest-confidence
non-None result for Gemini validation.

Adding a new strategy: create a class implementing BaseStrategy and add it
to STRATEGY_REGISTRY.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from app.services.scanner.indicators import (
    ema, rsi, macd, atr,
    swing_highs, swing_lows,
    support_resistance_levels,
    trend_structure,
    normalised_atr,
)

logger = logging.getLogger(__name__)


@dataclass
class CandidateSignal:
    """A pre-validated signal candidate from the strategy engine."""
    direction: str          # "buy" or "sell"
    entry_min: float
    entry_max: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: Optional[float]
    take_profit_3: Optional[float]
    risk_reward: float
    confidence: int         # 0–100 (strategy-level estimate, Gemini may adjust)
    strategy_id: str        # e.g. "ema_trend_pullback"
    strategy_name: str
    invalidation_condition: str
    reasoning: list[str]   # Short factual observations for Gemini context


class BaseStrategy(ABC):
    """Interface for all scanner strategies."""

    id: str
    name: str
    description: str

    @abstractmethod
    def scan(
        self,
        candles: list[dict],
        bid: float,
        ask: float,
        atr_value: Optional[float],
    ) -> Optional[CandidateSignal]:
        """
        Analyse the candle list and return a candidate signal or None.

        Do NOT call Gemini here.  Gemini is called later by the pipeline.
        """
        ...


# ---------------------------------------------------------------------------
# Strategy 1: EMA Trend + RSI Pullback
# ---------------------------------------------------------------------------

class EmaTrendPullbackStrategy(BaseStrategy):
    """
    Classic trend-following strategy with RSI-filtered pullback entry.

    Entry conditions (buy):
      - Price > EMA20 > EMA50 > EMA200 (trending up)
      - Price has pulled back toward EMA20
      - RSI is not overbought (< 65)
      - Last candle closed bullishly
      - ATR is adequate (avoiding dead markets)

    Entry conditions (sell):
      - Symmetric inverse
    """

    id = "ema_trend_pullback"
    name = "EMA Trend Pullback"
    description = "Trend-following with EMA alignment and RSI pullback filter"

    def scan(
        self,
        candles: list[dict],
        bid: float,
        ask: float,
        atr_value: Optional[float],
    ) -> Optional[CandidateSignal]:
        if len(candles) < 205:
            return None

        closes = [c["close"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]

        e20 = ema(closes, 20)
        e50 = ema(closes, 50)
        e200 = ema(closes, 200)
        rsi_val = rsi(closes, 14)
        macd_val = macd(closes)
        current_close = closes[-1]
        prev_close = closes[-2]
        atr_val = atr_value or atr(candles, 14)

        if any(v is None for v in [e20, e50, e200, rsi_val, atr_val]):
            return None

        if atr_val <= 0:
            return None

        # ----------------------------------------------------------------
        # BUY setup
        # ----------------------------------------------------------------
        if (
            e20 > e50 > e200
            and current_close > e20
            and rsi_val < 65
            and current_close > prev_close  # bullish close
            and macd_val and macd_val["histogram"] > 0
        ):
            # Entry zone: current bid ± 0.5 ATR
            entry_min = round(bid - atr_val * 0.2, 5)
            entry_max = round(ask + atr_val * 0.1, 5)
            stop_loss = round(min(lows[-5:]) - atr_val * 0.3, 5)

            sl_dist = entry_min - stop_loss
            if sl_dist <= 0:
                return None

            tp1 = round(entry_max + sl_dist * 1.5, 5)
            tp2 = round(entry_max + sl_dist * 2.5, 5)
            tp3 = round(entry_max + sl_dist * 4.0, 5)
            rr = (tp1 - entry_max) / sl_dist if sl_dist > 0 else 0

            if rr < 1.5:
                return None

            return CandidateSignal(
                direction="buy",
                entry_min=entry_min,
                entry_max=entry_max,
                stop_loss=stop_loss,
                take_profit_1=tp1,
                take_profit_2=tp2,
                take_profit_3=tp3,
                risk_reward=round(rr, 2),
                confidence=65,
                strategy_id=self.id,
                strategy_name=self.name,
                invalidation_condition=f"Candle closes below EMA50 ({e50:.5f})",
                reasoning=[
                    f"EMA alignment bullish: EMA20 {e20:.5f} > EMA50 {e50:.5f} > EMA200 {e200:.5f}",
                    f"RSI {rsi_val:.1f} — not overbought, pullback potential",
                    f"MACD histogram positive {macd_val['histogram']:.5f}" if macd_val else "MACD positive",
                    f"Last candle closed bullishly above EMA20",
                    f"Stop below 5-bar swing low with {atr_val * 0.3:.5f} buffer",
                ],
            )

        # ----------------------------------------------------------------
        # SELL setup
        # ----------------------------------------------------------------
        if (
            e20 < e50 < e200
            and current_close < e20
            and rsi_val > 35
            and current_close < prev_close  # bearish close
            and macd_val and macd_val["histogram"] < 0
        ):
            entry_max = round(ask + atr_val * 0.2, 5)
            entry_min = round(bid - atr_val * 0.1, 5)
            stop_loss = round(max(highs[-5:]) + atr_val * 0.3, 5)

            sl_dist = stop_loss - entry_max
            if sl_dist <= 0:
                return None

            tp1 = round(entry_min - sl_dist * 1.5, 5)
            tp2 = round(entry_min - sl_dist * 2.5, 5)
            tp3 = round(entry_min - sl_dist * 4.0, 5)
            rr = (entry_min - tp1) / sl_dist if sl_dist > 0 else 0

            if rr < 1.5:
                return None

            return CandidateSignal(
                direction="sell",
                entry_min=entry_min,
                entry_max=entry_max,
                stop_loss=stop_loss,
                take_profit_1=tp1,
                take_profit_2=tp2,
                take_profit_3=tp3,
                risk_reward=round(rr, 2),
                confidence=65,
                strategy_id=self.id,
                strategy_name=self.name,
                invalidation_condition=f"Candle closes above EMA50 ({e50:.5f})",
                reasoning=[
                    f"EMA alignment bearish: EMA20 {e20:.5f} < EMA50 {e50:.5f} < EMA200 {e200:.5f}",
                    f"RSI {rsi_val:.1f} — not oversold, continuation possible",
                    f"MACD histogram negative {macd_val['histogram']:.5f}" if macd_val else "MACD negative",
                    f"Last candle closed bearishly below EMA20",
                    f"Stop above 5-bar swing high with {atr_val * 0.3:.5f} buffer",
                ],
            )

        return None


# ---------------------------------------------------------------------------
# Strategy 2: Support/Resistance Bounce
# ---------------------------------------------------------------------------

class SupportResistanceBounceStrategy(BaseStrategy):
    """
    Identifies price bouncing off key S/R levels with RSI confirmation.
    """

    id = "sr_bounce"
    name = "Support/Resistance Bounce"
    description = "Price testing and bouncing off key S/R levels"

    def scan(
        self,
        candles: list[dict],
        bid: float,
        ask: float,
        atr_value: Optional[float],
    ) -> Optional[CandidateSignal]:
        if len(candles) < 50:
            return None

        closes = [c["close"] for c in candles]
        rsi_val = rsi(closes, 14)
        atr_val = atr_value or atr(candles, 14)

        if rsi_val is None or atr_val is None or atr_val <= 0:
            return None

        sr = support_resistance_levels(candles, lookback=5)
        current_close = closes[-1]
        tolerance = atr_val * 0.5

        # Check buy at support
        for support in sr["support"][:3]:
            if abs(current_close - support) <= tolerance and rsi_val < 45:
                stop_loss = round(support - atr_val * 1.0, 5)
                entry_min = round(bid - atr_val * 0.1, 5)
                entry_max = round(ask + atr_val * 0.1, 5)

                # Find nearest resistance as TP1
                resistances_above = [r for r in sr["resistance"] if r > entry_max]
                if not resistances_above:
                    continue
                tp1 = resistances_above[0]

                sl_dist = entry_min - stop_loss
                if sl_dist <= 0:
                    continue

                rr = (tp1 - entry_max) / sl_dist
                if rr < 1.5:
                    continue

                return CandidateSignal(
                    direction="buy",
                    entry_min=entry_min,
                    entry_max=entry_max,
                    stop_loss=stop_loss,
                    take_profit_1=tp1,
                    take_profit_2=round(tp1 + (tp1 - entry_max) * 0.5, 5) if tp1 else None,
                    take_profit_3=None,
                    risk_reward=round(rr, 2),
                    confidence=60,
                    strategy_id=self.id,
                    strategy_name=self.name,
                    invalidation_condition=f"Candle closes below support {support:.5f}",
                    reasoning=[
                        f"Price testing support at {support:.5f}",
                        f"RSI {rsi_val:.1f} suggests oversold conditions near support",
                        f"Next resistance at {tp1:.5f} provides {rr:.1f}R target",
                    ],
                )

        # Check sell at resistance
        for resistance in sr["resistance"][-3:]:
            if abs(current_close - resistance) <= tolerance and rsi_val > 55:
                stop_loss = round(resistance + atr_val * 1.0, 5)
                entry_min = round(bid - atr_val * 0.1, 5)
                entry_max = round(ask + atr_val * 0.1, 5)

                supports_below = [s for s in sr["support"] if s < entry_min]
                if not supports_below:
                    continue
                tp1 = supports_below[0]

                sl_dist = stop_loss - entry_max
                if sl_dist <= 0:
                    continue

                rr = (entry_min - tp1) / sl_dist
                if rr < 1.5:
                    continue

                return CandidateSignal(
                    direction="sell",
                    entry_min=entry_min,
                    entry_max=entry_max,
                    stop_loss=stop_loss,
                    take_profit_1=tp1,
                    take_profit_2=round(tp1 - (entry_min - tp1) * 0.5, 5) if tp1 else None,
                    take_profit_3=None,
                    risk_reward=round(rr, 2),
                    confidence=60,
                    strategy_id=self.id,
                    strategy_name=self.name,
                    invalidation_condition=f"Candle closes above resistance {resistance:.5f}",
                    reasoning=[
                        f"Price testing resistance at {resistance:.5f}",
                        f"RSI {rsi_val:.1f} suggests overbought conditions at resistance",
                        f"Support at {tp1:.5f} provides {rr:.1f}R target",
                    ],
                )

        return None


# ---------------------------------------------------------------------------
# Strategy Registry
# ---------------------------------------------------------------------------

STRATEGY_REGISTRY: dict[str, BaseStrategy] = {
    EmaTrendPullbackStrategy.id: EmaTrendPullbackStrategy(),
    SupportResistanceBounceStrategy.id: SupportResistanceBounceStrategy(),
}


def get_strategy(strategy_id: str) -> Optional[BaseStrategy]:
    return STRATEGY_REGISTRY.get(strategy_id)


def list_strategies() -> list[dict]:
    return [
        {"id": s.id, "name": s.name, "description": s.description}
        for s in STRATEGY_REGISTRY.values()
    ]


def run_all_strategies(
    candles: list[dict],
    bid: float,
    ask: float,
    enabled_strategy_ids: Optional[list[str]] = None,
) -> Optional[CandidateSignal]:
    """
    Run all enabled strategies and return the highest-confidence candidate.
    Returns None if no setup is found.
    """
    atr_val = atr(candles, 14)
    best: Optional[CandidateSignal] = None

    strategies_to_run = (
        [STRATEGY_REGISTRY[sid] for sid in enabled_strategy_ids if sid in STRATEGY_REGISTRY]
        if enabled_strategy_ids
        else list(STRATEGY_REGISTRY.values())
    )

    for strategy in strategies_to_run:
        try:
            candidate = strategy.scan(candles, bid, ask, atr_val)
            if candidate is not None:
                if best is None or candidate.confidence > best.confidence:
                    best = candidate
        except Exception as exc:
            logger.warning("Strategy %s raised an error: %s", strategy.id, exc)

    return best
